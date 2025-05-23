# rag/langgraph_vis/sse_handler.py
import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from .schemas import (
    GraphExecutionStartEvent,
    NodeStartEvent,
    NodeEndEvent,
    EdgeTakenEvent,
    GraphExecutionEndEvent,
    GraphErrorEvent,
)
from .core.builder import DynamicGraphBuilder, DynamicGraphBuilderError
from .core.definitions import STATIC_GRAPHS_METADATA
from .api_routes import _load_graph_definition_from_file

logger = logging.getLogger(__name__)
router = APIRouter()

async def event_generator(
    graph_id: str,
    execution_id: str,
    input_args: Dict[str, Any],
    simulation_delay_ms: Optional[int] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate SSE events for graph execution."""
    
    try:
        # Load and build the graph
        compiled_graph = None
        if graph_id.startswith("static_"):
            static_graph_name = graph_id[len("static_"):]
            if static_graph_name in STATIC_GRAPHS_METADATA:
                compiled_graph = STATIC_GRAPHS_METADATA[static_graph_name]["compiled_graph"]
            else:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "eventType": "graph_error",
                        "executionId": execution_id,
                        "graphId": graph_id,
                        "message": f"Static graph '{static_graph_name}' not found.",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
                return
        else:
            graph_def = _load_graph_definition_from_file(graph_id)
            if not graph_def:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "eventType": "graph_error",
                        "executionId": execution_id,
                        "graphId": graph_id,
                        "message": f"Graph definition ID '{graph_id}' not found.",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
                return
            
            try:
                compiled_graph = DynamicGraphBuilder(graph_def).build()
            except DynamicGraphBuilderError as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "eventType": "graph_error",
                        "executionId": execution_id,
                        "graphId": graph_id,
                        "message": f"Failed to build graph: {str(e)}",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
                return

        # Send start event
        start_event = GraphExecutionStartEvent(
            execution_id=execution_id,
            graph_id=graph_id,
            input_args=input_args
        )
        yield {
            "event": "graph_execution_start",
            "data": start_event.model_dump_json(by_alias=True)
        }

        # Prepare execution config
        execution_config = {"recursion_limit": 25}
        if simulation_delay_ms is not None:
            execution_config["simulation_delay_ms"] = simulation_delay_ms

        # Stream graph execution events
        async for event_chunk in compiled_graph.astream_events(
            input_args,
            version="v2",
            config=execution_config
        ):
            event_type = event_chunk["event"]
            event_data = event_chunk.get("data", {})
            event_name = event_chunk.get("name", "")
            tags = event_chunk.get("tags", [])

            # Map LangGraph events to our SSE events
            if "langgraph:node:" + event_name in tags:
                if event_type in ["on_chain_start", "on_tool_start", "on_chat_model_start"]:
                    node_start_event = NodeStartEvent(
                        execution_id=execution_id,
                        graph_id=graph_id,
                        node_id=event_name,
                        input_data=event_data.get("input", event_data.get("input_str", {}))
                    )
                    yield {
                        "event": "node_start",
                        "data": node_start_event.model_dump_json(by_alias=True)
                    }
                
                elif event_type in ["on_chain_end", "on_tool_end", "on_chat_model_end"]:
                    status = "success"
                    error_msg = None
                    output = event_data.get("output", {})
                    
                    if isinstance(output, Exception):
                        status = "failure"
                        error_msg = str(output)
                    
                    node_end_event = NodeEndEvent(
                        execution_id=execution_id,
                        graph_id=graph_id,
                        node_id=event_name,
                        output_data=output if status == "success" else {"error": error_msg},
                        status=status,
                        error_message=error_msg
                    )
                    yield {
                        "event": "node_end",
                        "data": node_end_event.model_dump_json(by_alias=True)
                    }

        # Send completion event
        final_state_data = event_chunk.get("data", {}).get("output", {}) if 'event_chunk' in locals() else {}
        graph_end_event = GraphExecutionEndEvent(
            execution_id=execution_id,
            graph_id=graph_id,
            final_state=final_state_data,
            status="completed"
        )
        yield {
            "event": "graph_execution_end",
            "data": graph_end_event.model_dump_json(by_alias=True)
        }

    except Exception as e:
        logger.error(f"Error during SSE stream for execution '{execution_id}': {e}", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({
                "eventType": "graph_error",
                "executionId": execution_id,
                "graphId": graph_id,
                "message": "An unexpected error occurred during graph execution.",
                "details": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        }

@router.post("/graphs/{graph_id}/execute/stream")
async def execute_graph_sse(
    graph_id: str,
    request_body: Dict[str, Any] = {},
):
    """Execute a graph and stream events via SSE."""
    execution_id = f"sse_exec_{uuid.uuid4().hex[:12]}"
    input_args = request_body.get("inputArgs", {})
    simulation_delay_ms = request_body.get("simulation_delay_ms")
    
    logger.info(f"SSE execution request for graph '{graph_id}' with execution_id '{execution_id}'")
    
    return EventSourceResponse(
        event_generator(graph_id, execution_id, input_args, simulation_delay_ms),
        headers={
            "Cache-Control": "no-cache",
            "X-Execution-ID": execution_id,
        }
    )