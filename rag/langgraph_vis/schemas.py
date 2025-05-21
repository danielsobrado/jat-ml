# rag/langgraph_vis/schemas.py
from __future__ import annotations # Enables postponed evaluation of type annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# --- Graph Definition Models (for saving/loading graph structures) ---

class NodeUIPosition(BaseModel):
    """Represents the UI position of a node for visualization."""
    x: float = Field(..., description="X-coordinate of the node in the UI.")
    y: float = Field(..., description="Y-coordinate of the node in the UI.")

class NodeDefinition(BaseModel):
    """Defines a single node in the graph structure."""
    id: str = Field(..., description="Unique identifier for the node (e.g., 'llm_formatter').")
    type: str = Field(..., description="Type of the node (e.g., 'llm_node', 'tool_node', 'router_node', 'entry_point', 'end_point'). This maps to backend logic.")
    config: Dict[str, Any] = Field(default_factory=dict, description="Configuration specific to this node type (e.g., LLM prompts, tool names, router logic keys).")
    ui_position: Optional[NodeUIPosition] = Field(None, description="Optional UI positioning hints for frontend rendering.")

class EdgeDefinition(BaseModel):
    """Defines a directed edge between two nodes in the graph structure."""
    id: str = Field(..., description="Unique identifier for the edge (e.g., 'e_llm_to_tool').")
    source: str = Field(..., description="ID of the source node.")
    target: str = Field(..., description="ID of the target node.")
    label: Optional[str] = Field(None, description="Optional label for the edge, often used for conditions or clarity.")
    animated: Optional[bool] = Field(False, description="Hint for UI to animate the edge.")
    # type: Optional[str] = Field(None, description="Optional edge type for custom React Flow rendering (e.g., 'custom_edge').")

class ConditionalEdgeMapping(BaseModel):
    """Defines the target node for a specific condition name."""
    condition_name: str = Field(..., description="The name of the condition (e.g., output value from a router node).")
    target_node_id: str = Field(..., description="The ID of the node to transition to if this condition is met.")

class ConditionalEdgesDefinition(BaseModel):
    """Defines conditional outgoing edges for a specific source node."""
    source_node_id: str = Field(..., description="The ID of the node that has conditional branches.")
    # condition_logic_key: Optional[str] = Field(None, description="Optional: Key in the graph state that the router node's logic uses to determine the condition_name.")
    mappings: List[ConditionalEdgeMapping] = Field(..., description="A list of condition-to-target mappings.")

class GraphDefinition(BaseModel):
    """Full definition of a LangGraph workflow, suitable for serialization (e.g., to JSON)."""
    id: str = Field(default_factory=lambda: f"graph_{uuid.uuid4()}", description="Unique identifier for the graph definition.")
    name: str = Field(..., description="Human-readable name for the graph.")
    description: Optional[str] = Field(None, description="Optional detailed description of the graph's purpose.")
    # LangGraph state schema is Pydantic model. We reference its *name* here.
    # The backend's dynamic_graph_builder will use this name to look up the actual Pydantic model.
    state_schema_name: str = Field(..., description="Name of the Pydantic model representing the LangGraph's state (must be known to the backend).")
    nodes: List[NodeDefinition] = Field(..., description="List of all nodes in the graph.")
    edges: List[EdgeDefinition] = Field(default_factory=list, description="List of all standard (non-conditional) edges.")
    conditional_edges: List[ConditionalEdgesDefinition] = Field(default_factory=list, description="List of conditional edge configurations.")
    entry_point_node_id: str = Field(..., description="ID of the node that serves as the entry point to the graph.")
    # Explicit 'END' nodes are handled by LangGraph. This field can list nodes that directly connect to END.
    # Or, nodes that have no outgoing edges defined here could be implicitly connected to END by the builder.
    # For clarity, let's allow defining nodes that should always transition to END if they are terminal.
    terminal_node_ids: Optional[List[str]] = Field(default_factory=list, description="Optional: List of node IDs that should implicitly transition to the global END state if they don't have other outgoing edges.")
    version: int = Field(1, description="Version of this graph definition structure.")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of creation.")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of last update.")

    @field_validator('updated_at', mode='before')
    @classmethod
    def set_updated_at_on_update(cls, v, values): # type: ignore[no-untyped-def]
        # Pydantic v1 style validator, will update to v2 if using model_validator
        # For now, this doesn't automatically update on modification through Pydantic.
        # Actual update logic will be in the API when saving.
        return v or datetime.utcnow()

# --- WebSocket Event Models (for real-time execution updates) ---

class WebSocketEventBase(BaseModel):
    """Base model for all WebSocket events."""
    event_type: str = Field(..., description="Type of the event.")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of when the event occurred.")
    execution_id: str = Field(..., description="Unique ID for this particular graph execution run.")
    graph_id: str = Field(..., description="ID of the graph definition being executed.")

class GraphExecutionStartEvent(WebSocketEventBase):
    event_type: Literal["graph_execution_start"] = "graph_execution_start"
    input_args: Dict[str, Any] = Field(..., description="Initial input arguments provided to the graph.")

class NodeLifecycleEvent(WebSocketEventBase):
    """Base for node-specific events."""
    node_id: str = Field(..., description="ID of the node this event pertains to.")
    node_type: Optional[str] = Field(None, description="Type of the node (e.g., 'llm_node').") # Can be useful for frontend

class NodeStartEvent(NodeLifecycleEvent):
    event_type: Literal["node_start"] = "node_start"
    input_data: Dict[str, Any] = Field(..., description="Data passed as input to this node iteration.")

class NodeEndEvent(NodeLifecycleEvent):
    event_type: Literal["node_end"] = "node_end"
    output_data: Dict[str, Any] = Field(..., description="Data produced as output by this node iteration.")
    status: Literal["success", "failure"] = Field(..., description="Execution status of the node.")
    error_message: Optional[str] = Field(None, description="Error message if the node execution failed.")
    duration_ms: Optional[float] = Field(None, description="Execution duration of the node in milliseconds.")

class EdgeTakenEvent(WebSocketEventBase):
    event_type: Literal["edge_taken"] = "edge_taken"
    source_node_id: str = Field(..., description="ID of the source node of the traversed edge.")
    target_node_id: str = Field(..., description="ID of the target node of the traversed edge.")
    edge_label: Optional[str] = Field(None, description="Label of the edge taken (e.g., condition name).")
    is_conditional: bool = Field(..., description="True if this was a conditional edge.")

class GraphExecutionEndEvent(WebSocketEventBase):
    event_type: Literal["graph_execution_end"] = "graph_execution_end"
    final_state: Dict[str, Any] = Field(..., description="The final state of the graph upon completion.")
    status: Literal["completed", "failed", "interrupted"] = Field(..., description="Overall status of the graph execution.")
    total_duration_ms: Optional[float] = Field(None, description="Total execution duration of the graph in milliseconds.")

class GraphErrorEvent(WebSocketEventBase):
    event_type: Literal["graph_error"] = "graph_error"
    message: str = Field(..., description="General error message related to graph execution.")
    details: Optional[str] = Field(None, description="Additional details or stack trace for the error.")
    node_id: Optional[str] = Field(None, description="ID of the node where the error occurred, if applicable.")

# --- API Request/Response Models (for HTTP endpoints) ---

class GraphDefinitionIdentifier(BaseModel):
    """Minimal information to identify a graph definition."""
    id: str = Field(..., description="Unique ID of the graph definition.")
    name: str = Field(..., description="Name of the graph definition.")
    updated_at: datetime = Field(..., description="Last update timestamp.")

class GraphDefinitionListResponse(BaseModel):
    """Response model for listing available graph definitions."""
    graphs: List[GraphDefinitionIdentifier] = Field(..., description="List of available graph definitions.")

class CreateGraphRequest(BaseModel):
    """Request to create a new graph definition. Most fields from GraphDefinition, ID is generated."""
    name: str = Field(..., description="Human-readable name for the graph.")
    description: Optional[str] = Field(None, description="Optional detailed description of the graph's purpose.")
    state_schema_name: str = Field(..., description="Name of the Pydantic model representing the LangGraph's state.")
    nodes: List[NodeDefinition] = Field(..., description="List of all nodes in the graph.")
    edges: List[EdgeDefinition] = Field(default_factory=list, description="List of all standard (non-conditional) edges.")
    conditional_edges: List[ConditionalEdgesDefinition] = Field(default_factory=list, description="List of conditional edge configurations.")
    entry_point_node_id: str = Field(..., description="ID of the node that serves as the entry point to the graph.")
    terminal_node_ids: Optional[List[str]] = Field(default_factory=list, description="Optional: List of node IDs that should implicitly transition to the global END state.")

    # Example of how you might want to model this if you are providing the full definition on creation,
    # but often ID, created_at, updated_at are server-generated.
    # For this, we'll assume the user provides the core structure and server adds metadata.

class UpdateGraphRequest(CreateGraphRequest): # Inherits fields from CreateGraphRequest
    """Request to update an existing graph definition. Includes all structural fields."""
    # ID will be in the path, name can be updated.
    pass

# GraphDefinition itself can serve as the response for GET /graph/{graph_id}

class ExecuteGraphRequest(BaseModel):
    """Request to initiate execution of a graph."""
    # graph_id will typically be a path parameter
    input_args: Dict[str, Any] = Field(default_factory=dict, description="Initial input arguments for the graph execution.")
    # config_overrides: Optional[Dict[str, Any]] = Field(None, description="Optional overrides for graph execution configuration.")

class ExecuteGraphResponse(BaseModel):
    """Response after initiating a graph execution (e.g., via HTTP if not solely WebSocket)."""
    execution_id: str = Field(..., description="Unique ID for the initiated graph execution run.")
    message: str = Field("Graph execution started. Follow WebSocket for updates.", description="Status message.")
    websocket_url: Optional[str] = Field(None, description="URL for the WebSocket connection to stream events for this execution.")

# Generic success/error messages
class MessageResponse(BaseModel):
    message: str

class ErrorDetail(BaseModel):
    loc: Optional[List[str | int]] = None
    msg: str
    type: str

class HTTPErrorResponse(BaseModel):
    detail: str | List[ErrorDetail]