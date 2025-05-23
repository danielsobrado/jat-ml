import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime
import uuid

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from .schemas import (
    GraphExecutionStartEvent,
    NodeStartEvent,
    NodeEndEvent,
    GraphExecutionEndEvent,
    GraphErrorEvent,
    ExecuteGraphRequest,
)
from .core.builder import DynamicGraphBuilder, DynamicGraphBuilderError
from .core.definitions import STATIC_GRAPHS_METADATA
from .api_routes import _load_graph_definition_from_file

logger = logging.getLogger(__name__)
try:
    from .ws_handler import CustomJSONEncoder
except ImportError:
    logger.warning("CustomJSONEncoder not found in ws_handler. Using basic json.JSONEncoder.")
    CustomJSONEncoder = json.JSONEncoder

router = APIRouter()


async def event_generator(
    graph_id: str,
    execution_id: str,
    input_args: Dict[str, Any],
    simulation_delay_ms: Optional[int] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate SSE events for graph execution."""

    def format_sse_data(event_model_instance):
        return json.dumps(event_model_instance.model_dump(mode="json", by_alias=True), cls=CustomJSONEncoder)

    try:
        compiled_graph = None
        if graph_id.startswith("static_"):
            static_graph_name = graph_id[len("static_"):]
            if static_graph_name in STATIC_GRAPHS_METADATA:
                compiled_graph = STATIC_GRAPHS_METADATA[static_graph_name]["compiled_graph"]
            else:
                error_payload_dict = {
                    "eventType": "graph_error", "executionId": execution_id, "graphId": graph_id,
                    "message": f"Static graph '{static_graph_name}' not found.",
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield {"event": "graph_error", "data": json.dumps(error_payload_dict, cls=CustomJSONEncoder)}
                return
        else:
            graph_def = _load_graph_definition_from_file(graph_id)
            if not graph_def:
                error_payload_dict = {
                    "eventType": "graph_error", "executionId": execution_id, "graphId": graph_id,
                    "message": f"Graph definition ID '{graph_id}' not found.",
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield {"event": "graph_error", "data": json.dumps(error_payload_dict, cls=CustomJSONEncoder)}
                return
            try:
                compiled_graph = DynamicGraphBuilder(graph_def).build()
            except DynamicGraphBuilderError as e:
                error_payload_dict = {
                    "eventType": "graph_error", "executionId": execution_id, "graphId": graph_id,
                    "message": f"Failed to build graph: {str(e)}",
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield {"event": "graph_error", "data": json.dumps(error_payload_dict, cls=CustomJSONEncoder)}
                return

        if not compiled_graph:
            error_payload_dict = {
                "eventType": "graph_error", "executionId": execution_id, "graphId": graph_id,
                "message": "Graph could not be compiled or loaded.",
                "timestamp": datetime.utcnow().isoformat()
            }
            yield {"event": "graph_error", "data": json.dumps(error_payload_dict, cls=CustomJSONEncoder)}
            return

        start_event = GraphExecutionStartEvent(
            execution_id=execution_id, graph_id=graph_id, input_args=input_args
        )
        yield {"event": "graph_execution_start", "data": format_sse_data(start_event)}

        execution_config = {"recursion_limit": 25}
        if simulation_delay_ms is not None:
            execution_config["simulation_delay_ms"] = simulation_delay_ms

        async for event_chunk in compiled_graph.astream_events(
            input_args, version="v2", config=execution_config
        ):
            event_type_lc = event_chunk["event"]
            event_data = event_chunk.get("data", {})
            event_name = event_chunk.get("name", "")
            tags = event_chunk.get("tags", [])
            node_id_from_tag = next((tag.split(":")[-1] for tag in tags if tag.startswith("langgraph:node:")), event_name)

            if any(tag.startswith("langgraph:node:") for tag in tags):
                if event_type_lc in ["on_chain_start", "on_tool_start", "on_chat_model_start"]:
                    node_start_event = NodeStartEvent(
                        execution_id=execution_id, graph_id=graph_id, node_id=node_id_from_tag,
                        input_data=event_data.get("input", event_data.get("input_str", {}))
                    )
                    yield {"event": "node_start", "data": format_sse_data(node_start_event)}

                elif event_type_lc in ["on_chain_end", "on_tool_end", "on_chat_model_end"]:
                    status_val = "success"
                    error_msg = None
                    output = event_data.get("output", {})
                    if isinstance(output, Exception):
                        status_val = "failure"; error_msg = str(output)

                    node_end_event = NodeEndEvent(
                        execution_id=execution_id, graph_id=graph_id, node_id=node_id_from_tag,
                        output_data=output if status_val == "success" else {"error": error_msg},
                        status=status_val, error_message=error_msg
                    )
                    yield {"event": "node_end", "data": format_sse_data(node_end_event)}

        final_state_data = event_chunk.get("data", {}).get("output", {}) if 'event_chunk' in locals() and event_chunk else {}
        graph_end_event = GraphExecutionEndEvent(
            execution_id=execution_id, graph_id=graph_id,
            final_state=final_state_data, status="completed"
        )
        yield {"event": "graph_execution_end", "data": format_sse_data(graph_end_event)}

    except Exception as e:
        logger.error(f"Error during SSE stream for execution '{execution_id}': {e}", exc_info=True)
        error_payload_dict = {
            "eventType": "graph_error", "executionId": execution_id, "graphId": graph_id,
            "message": "An unexpected error occurred during graph execution.",
            "details": str(e), "timestamp": datetime.utcnow().isoformat()
        }
        yield {"event": "graph_error", "data": json.dumps(error_payload_dict, cls=CustomJSONEncoder)}


@router.post("/graphs/{graph_id}/execute/stream")
async def execute_graph_sse(
    graph_id: str,
    request_body: ExecuteGraphRequest,
):
    """Execute a graph and stream events via SSE."""
    execution_id = f"sse_exec_{uuid.uuid4().hex[:12]}"
    input_args = request_body.input_args if request_body.input_args is not None else {}
    simulation_delay_ms = request_body.simulation_delay_ms

    logger.info(f"SSE execution request for graph '{graph_id}' with execution_id '{execution_id}'")

    return EventSourceResponse(
        event_generator(graph_id, execution_id, input_args, simulation_delay_ms),
        headers={
            "Cache-Control": "no-cache",
            "X-Execution-ID": execution_id,
        }
    )