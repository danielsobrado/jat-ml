# rag/langgraph_vis/stream_handler.py
import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse

from .schemas import (
    GraphExecutionStartEvent,
    NodeStartEvent,
    NodeEndEvent,
    EdgeTakenEvent,
    GraphExecutionEndEvent,
    GraphErrorEvent,
    ExecuteGraphRequest,
)
from .core.builder import DynamicGraphBuilder, DynamicGraphBuilderError
from .core.definitions import STATIC_GRAPHS_METADATA
from .api_routes import _load_graph_definition_from_file

logger = logging.getLogger(__name__)
router = APIRouter()

async def stream_graph_execution(
    graph_id: str,
    execution_id: str,
    input_args: Dict[str, Any],
    simulation_delay_ms: Optional[int] = None
) -> AsyncGenerator[bytes, None]:
    """Stream NDJSON (newline-delimited JSON) events for graph execution."""
    
    def serialize_event(event: Any) -> bytes:
        """Serialize event to NDJSON format (JSON + newline)."""
        return (event.model_dump_json(by_alias=True) + '\n').encode('utf-8')
    
    try:
        # Load and build the graph
        compiled_graph = None
        if graph_id.startswith("static_"):
            static_graph_name = graph_id[len("static_"):]
            if static_graph_name in STATIC_GRAPHS_METADATA:
                compiled_graph = STATIC_GRAPHS_METADATA[static_graph_name]["compiled_graph"]
            else:
                error_event = GraphErrorEvent(
                    execution_id=execution_id,
                    graph_id=graph_id,
                    message=f"Static graph '{static_graph_name}' not found.",
                    timestamp=datetime.utcnow()
                )
                yield serialize_event(error_event)
                return
        else:
            graph_def = _load_graph_definition_from_file(graph_id)
            if not graph_def:
                error_event = GraphErrorEvent(
                    execution_id=execution_id,
                    graph_id=graph_id,
                    message=f"Graph definition ID '{graph_id}' not found.",
                    timestamp=datetime.utcnow()
                )
                yield serialize_event(error_event)
                return
            
            try:
                compiled_graph = DynamicGraphBuilder(graph_def).build()
            except DynamicGraphBuilderError as e:
                error_event = GraphErrorEvent(
                    execution_id=execution_id,
                    graph_id=graph_id,
                    message=f"Failed to build graph: {str(e)}",
                    timestamp=datetime.utcnow()
                )
                yield serialize_event(error_event)
                return

        # Send start event
        start_event = GraphExecutionStartEvent(
            execution_id=execution_id,
            graph_id=graph_id,
            input_args=input_args
        )
        yield serialize_event(start_event)

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

            # Map LangGraph events to our streaming events
            if "langgraph:node:" + event_name in tags:
                if event_type in ["on_chain_start", "on_tool_start", "on_chat_model_start"]:
                    node_start_event = NodeStartEvent(
                        execution_id=execution_id,
                        graph_id=graph_id,
                        node_id=event_name,
                        input_data=event_data.get("input", event_data.get("input_str", {}))
                    )
                    yield serialize_event(node_start_event)
                
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
                    yield serialize_event(node_end_event)

            # Optional: Send edge events if you can detect them
            if "langgraph:edge" in tags:
                # Parse edge information from event
                edge_event = EdgeTakenEvent(
                    execution_id=execution_id,
                    graph_id=graph_id,
                    source_node_id=event_data.get("source", "unknown"),
                    target_node_id=event_data.get("target", "unknown"),
                    edge_label=event_data.get("label"),
                    is_conditional=event_data.get("conditional", False)
                )
                yield serialize_event(edge_event)

        # Send completion event
        final_state_data = event_chunk.get("data", {}).get("output", {}) if 'event_chunk' in locals() else {}
        graph_end_event = GraphExecutionEndEvent(
            execution_id=execution_id,
            graph_id=graph_id,
            final_state=final_state_data,
            status="completed"
        )
        yield serialize_event(graph_end_event)

    except Exception as e:
        logger.error(f"Error during stream for execution '{execution_id}': {e}", exc_info=True)
        error_event = GraphErrorEvent(
            execution_id=execution_id,
            graph_id=graph_id,
            message="An unexpected error occurred during graph execution.",
            details=str(e),
            timestamp=datetime.utcnow()
        )
        yield serialize_event(error_event)

@router.post("/graphs/{graph_id}/execute/stream")
async def execute_graph_stream(
    graph_id: str,
    request: ExecuteGraphRequest = Body(...)
):
    """Execute a graph and stream events as NDJSON."""
    execution_id = f"stream_exec_{uuid.uuid4().hex[:12]}"
    
    logger.info(f"Stream execution request for graph '{graph_id}' with execution_id '{execution_id}'")
    
    return StreamingResponse(
        stream_graph_execution(
            graph_id,
            execution_id,
            request.input_args or {},
            request.simulation_delay_ms
        ),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Execution-ID": execution_id,
            "X-Content-Type-Options": "nosniff",  # Security header
        }
    )