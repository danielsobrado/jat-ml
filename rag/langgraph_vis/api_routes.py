# rag/langgraph_vis/api_routes.py
import logging
import os
import json
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Body, Depends, Path as FastAPIPath, Query
from fastapi.responses import JSONResponse

# Assuming schemas.py is in the parent directory or accessible
from .schemas import (
    GraphDefinition,
    GraphDefinitionListResponse,
    GraphDefinitionIdentifier,
    CreateGraphRequest,
    UpdateGraphRequest,
    ExecuteGraphRequest, # If providing HTTP trigger for execution
    ExecuteGraphResponse, # If providing HTTP trigger for execution
    MessageResponse
)
# Assuming builder.py is in the core subdirectory
from .core.builder import DynamicGraphBuilder, DynamicGraphBuilderError
# Assuming definitions.py is in the core subdirectory for static graphs
from .core.definitions import STATIC_GRAPHS

# Placeholder for authentication dependency - replace with your actual auth
# from ....api.auth import get_current_active_user # Adjust import based on your project structure
# from ....config import config as app_config # Adjust for your main app config

# --- Temporary Auth Placeholder (until you integrate your main auth) ---
# If your main auth logic is in `rag.api.auth`, you'd import from there.
# For now, to make this runnable independently, let's use a dummy.
from fastapi import Security # For dummy auth
async def get_current_active_user_placeholder():
    # In a real app, this would validate a token and return a user model.
    # If auth is disabled in your main app, this could return a default user or None.
    # For testing, assume an admin user if no real auth is integrated here.
    class DummyUser:
        username: str = "test_admin"
        # Add other fields your User model might have if needed by endpoints
    # Check a hypothetical config:
    # if app_config.auth.enabled:
    #    raise HTTPException(status_code=401, detail="Not authenticated via main auth")
    return DummyUser()
# --- End Temporary Auth Placeholder ---

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Configuration for storing graph definitions ---
# TODO: Move this to a proper configuration file (e.g., your main rag/config.py)
# For now, define it here. This should be an absolute path in production.
GRAPH_DEFINITIONS_DIR = Path(os.getenv("GRAPH_DEFINITIONS_DIR", "data/graph_definitions"))
GRAPH_DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Graph definitions will be stored in: {GRAPH_DEFINITIONS_DIR.resolve()}")

# --- Helper Functions ---
def _get_graph_definition_path(graph_id: str) -> Path:
    """Constructs the file path for a given graph ID."""
    # Basic sanitization to prevent directory traversal, though graph_id should be UUID-like.
    # A more robust sanitization might be needed if graph_id can be arbitrary strings.
    if ".." in graph_id or "/" in graph_id or "\\" in graph_id:
        raise ValueError("Invalid characters in graph_id.")
    return GRAPH_DEFINITIONS_DIR / f"{graph_id}.json"

def _load_graph_definition_from_file(graph_id: str) -> GraphDefinition | None:
    """Loads a graph definition from its JSON file."""
    file_path = _get_graph_definition_path(graph_id)
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            return GraphDefinition(**data)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON for graph ID '{graph_id}' from {file_path}")
            return None
        except Exception as e: # Catch Pydantic validation errors too
            logger.error(f"Error loading/validating graph definition for graph ID '{graph_id}': {e}")
            return None
    return None

def _save_graph_definition_to_file(graph_def: GraphDefinition) -> None:
    """Saves a graph definition to a JSON file."""
    file_path = _get_graph_definition_path(graph_def.id)
    try:
        with open(file_path, "w") as f:
            json.dump(graph_def.model_dump(mode="json"), f, indent=2)
        logger.info(f"Saved graph definition '{graph_def.name}' (ID: {graph_def.id}) to {file_path}")
    except Exception as e:
        logger.error(f"Error saving graph definition ID '{graph_def.id}' to {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save graph definition: {str(e)}")

def _delete_graph_definition_file(graph_id: str) -> bool:
    """Deletes a graph definition file."""
    file_path = _get_graph_definition_path(graph_id)
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"Deleted graph definition file for ID '{graph_id}': {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting graph definition file for ID '{graph_id}': {e}")
            return False
    return False # File didn't exist

# --- API Endpoints ---

@router.post(
    "/graphs",
    response_model=GraphDefinition,
    status_code=201,
    summary="Create a new graph definition",
    dependencies=[Depends(get_current_active_user_placeholder)] # Replace with your actual auth
)
async def create_graph_definition(
    graph_create_request: CreateGraphRequest = Body(...)
):
    """
    Creates a new LangGraph workflow definition and saves it.
    The ID for the graph will be generated automatically.
    """
    logger.info(f"Received request to create graph: {graph_create_request.name}")
    # Create a full GraphDefinition model from the request
    # ID, created_at, updated_at are auto-generated by GraphDefinition model defaults
    graph_def = GraphDefinition(**graph_create_request.model_dump())

    # Validate that it can be built (optional, but good for early feedback)
    try:
        DynamicGraphBuilder(graph_def).build() # Try to build it to catch structural errors
        logger.info(f"Successfully test-built new graph definition: {graph_def.name}")
    except DynamicGraphBuilderError as e:
        logger.error(f"Validation error during test-build for new graph '{graph_def.name}': {e}")
        raise HTTPException(status_code=422, detail=f"Invalid graph structure: {str(e)}")

    _save_graph_definition_to_file(graph_def)
    return graph_def

@router.get(
    "/graphs",
    response_model=GraphDefinitionListResponse,
    summary="List all saved graph definitions"
)
async def list_graph_definitions(
    include_static: bool = Query(False, description="Include predefined static graphs in the listing")
):
    """
    Retrieves a list of identifiers for all saved LangGraph workflow definitions.
    """
    saved_graphs: List[GraphDefinitionIdentifier] = []
    for file_path in GRAPH_DEFINITIONS_DIR.glob("*.json"):
        graph_id = file_path.stem
        graph_def = _load_graph_definition_from_file(graph_id)
        if graph_def:
            saved_graphs.append(
                GraphDefinitionIdentifier(id=graph_def.id, name=graph_def.name, updated_at=graph_def.updated_at)
            )
    
    if include_static:
        for name, compiled_graph in STATIC_GRAPHS.items():
            # Static graphs don't have a full GraphDefinition file by default.
            # We'd need to either generate one or provide minimal info.
            # For now, let's create a mock identifier.
            # A better approach would be to also store a GraphDefinition JSON for static graphs if they need to be listed here.
            mock_id = f"static_{name}"
            if not any(g.id == mock_id for g in saved_graphs): # Avoid duplicates if somehow saved
                 saved_graphs.append(
                    GraphDefinitionIdentifier(
                        id=mock_id, # Placeholder ID for static graphs
                        name=f"[STATIC] {name.replace('_', ' ').title()}",
                        updated_at=compiled_graph.compiled_at if hasattr(compiled_graph, 'compiled_at') else None # type: ignore
                    )
                )

    return GraphDefinitionListResponse(graphs=saved_graphs)

@router.get(
    "/graphs/{graph_id}",
    response_model=GraphDefinition, # Returns the full definition
    summary="Get a specific graph definition"
)
async def get_graph_definition(
    graph_id: str = FastAPIPath(..., description="The ID of the graph definition to retrieve.")
):
    """
    Retrieves the full JSON definition of a specific LangGraph workflow.
    """
    logger.debug(f"Request to get graph definition for ID: {graph_id}")
    
    # Check if it's a request for a static graph
    if graph_id.startswith("static_"):
        static_graph_name = graph_id[len("static_"):]
        if static_graph_name in STATIC_GRAPHS:
            # This is tricky: STATIC_GRAPHS holds CompiledGraph. We need to return a GraphDefinition.
            # Ideally, you'd have the GraphDefinition JSON also for static graphs if you want to serve them this way.
            # For now, raise an error or return a simplified/mocked-up GraphDefinition.
            raise HTTPException(status_code=404, detail=f"Cannot retrieve full GraphDefinition for static graph '{static_graph_name}' via this endpoint. Execute it directly or provide its JSON definition.")
            # Or, you could construct a minimal GraphDefinition if needed.

    graph_def = _load_graph_definition_from_file(graph_id)
    if not graph_def:
        raise HTTPException(status_code=404, detail=f"Graph definition with ID '{graph_id}' not found.")
    return graph_def

@router.put(
    "/graphs/{graph_id}",
    response_model=GraphDefinition,
    summary="Update an existing graph definition",
    dependencies=[Depends(get_current_active_user_placeholder)] # Replace with your actual auth
)
async def update_graph_definition(
    graph_id: str = FastAPIPath(..., description="The ID of the graph definition to update."),
    graph_update_request: UpdateGraphRequest = Body(...)
):
    """
    Updates an existing LangGraph workflow definition.
    The entire graph structure is replaced with the provided data.
    """
    logger.info(f"Received request to update graph ID: {graph_id}")
    existing_graph_def = _load_graph_definition_from_file(graph_id)
    if not existing_graph_def:
        raise HTTPException(status_code=404, detail=f"Graph definition with ID '{graph_id}' not found for update.")

    # Create the updated GraphDefinition model
    # Preserve original ID and created_at, update other fields and updated_at
    updated_graph_data = graph_update_request.model_dump()
    updated_graph_data["id"] = existing_graph_def.id # Ensure ID doesn't change
    updated_graph_data["created_at"] = existing_graph_def.created_at # Preserve original creation time
    updated_graph_data["updated_at"] = None # Will be set by GraphDefinition model default_factory or manually

    updated_graph_def = GraphDefinition(**updated_graph_data)
    updated_graph_def.updated_at = updated_graph_def.model_fields['updated_at'].default_factory() # Force update timestamp

    # Validate that the updated definition can be built
    try:
        DynamicGraphBuilder(updated_graph_def).build()
        logger.info(f"Successfully test-built updated graph definition: {updated_graph_def.name}")
    except DynamicGraphBuilderError as e:
        logger.error(f"Validation error during test-build for updated graph '{updated_graph_def.name}': {e}")
        raise HTTPException(status_code=422, detail=f"Invalid graph structure: {str(e)}")

    _save_graph_definition_to_file(updated_graph_def)
    return updated_graph_def

@router.delete(
    "/graphs/{graph_id}",
    response_model=MessageResponse,
    status_code=200, # Or 204 No Content if not returning a message
    summary="Delete a graph definition",
    dependencies=[Depends(get_current_active_user_placeholder)] # Replace with your actual auth
)
async def delete_graph_definition(
    graph_id: str = FastAPIPath(..., description="The ID of the graph definition to delete.")
):
    """
    Deletes a saved LangGraph workflow definition.
    Static graphs cannot be deleted via this endpoint.
    """
    logger.info(f"Request to delete graph definition ID: {graph_id}")
    if graph_id.startswith("static_"):
        raise HTTPException(status_code=400, detail="Static graph definitions cannot be deleted via this API.")

    if not _delete_graph_definition_file(graph_id):
        # Check if it existed before trying to delete, to return proper 404
        if _get_graph_definition_path(graph_id).exists(): # Path exists but deletion failed
             raise HTTPException(status_code=500, detail=f"Failed to delete graph definition file for ID '{graph_id}'.")
        raise HTTPException(status_code=404, detail=f"Graph definition with ID '{graph_id}' not found.")
    
    return MessageResponse(message=f"Graph definition with ID '{graph_id}' deleted successfully.")


# Optional: Endpoint to trigger execution via HTTP (less ideal than WebSocket for streaming)
# This is often used if you just want to kick off a graph and get a final result,
# or if the client doesn't support WebSockets for some reason.
@router.post(
    "/graphs/{graph_id}/execute",
    response_model=ExecuteGraphResponse, # Could also return final state if execution is blocking & quick
    summary="Trigger execution of a graph (non-streaming)",
    dependencies=[Depends(get_current_active_user_placeholder)] # Replace with your actual auth
)
async def execute_graph_http(
    graph_id: str = FastAPIPath(..., description="ID of the graph to execute (saved or static)."),
    request: ExecuteGraphRequest = Body(...),
    # You might need to inject the WebSocket URL or some context here if this HTTP
    # endpoint is just a trigger for a WebSocket-based execution.
    # For example, from `request.url_for` if WebSockets are hosted by the same app.
):
    """
    Initiates the execution of a specified LangGraph workflow.
    This endpoint is primarily for triggering. For real-time updates,
    clients should connect to the WebSocket endpoint.
    """
    logger.info(f"HTTP request to execute graph ID: {graph_id} with inputs: {request.input_args}")

    # This endpoint would typically:
    # 1. Load/Build the graph (from file or static registry).
    # 2. Generate a unique execution ID.
    # 3. Store the execution request or kick off the graph run (potentially in a background task).
    # 4. Return the execution ID and WebSocket URL for the client to connect.
    
    # For this example, we'll just simulate the response.
    # The actual graph execution logic will be tied to the WebSocket handler.
    
    # Check if graph exists (saved or static)
    compiled_graph = None
    if graph_id.startswith("static_"):
        static_graph_name = graph_id[len("static_"):]
        if static_graph_name in STATIC_GRAPHS:
            compiled_graph = STATIC_GRAPHS[static_graph_name]
        else:
            raise HTTPException(status_code=404, detail=f"Static graph '{static_graph_name}' not found.")
    else:
        graph_def = _load_graph_definition_from_file(graph_id)
        if not graph_def:
            raise HTTPException(status_code=404, detail=f"Graph definition ID '{graph_id}' not found.")
        try:
            compiled_graph = DynamicGraphBuilder(graph_def).build()
        except DynamicGraphBuilderError as e:
            raise HTTPException(status_code=500, detail=f"Failed to build graph '{graph_id}': {str(e)}")

    if not compiled_graph: # Should be caught above, but defensive
        raise HTTPException(status_code=500, detail=f"Could not load or build graph '{graph_id}'.")

    # In a real scenario, you'd now pass this `compiled_graph` and `request.input_args`
    # to your WebSocket execution manager or a background task runner.
    # For now, we just return a response indicating it's "started".
    execution_id = f"exec_{os.urandom(8).hex()}" # Example execution ID
    
    # Construct the WebSocket URL - this depends on how/where your WS is hosted
    # If hosted by the same FastAPI app:
    # ws_url = request.url_for("websocket_execute_graph", graph_id=graph_id, execution_id=execution_id)
    # For now, placeholder:
    ws_url_placeholder = f"/ws/langgraph/graphs/{graph_id}/execute/{execution_id}" # Adjust path as per your ws_handler.py

    logger.info(f"Generated execution ID '{execution_id}' for graph '{graph_id}'. Client should connect to WebSocket.")

    return ExecuteGraphResponse(
        execution_id=execution_id,
        message=f"Graph execution '{execution_id}' initiated for graph '{graph_id}'. Connect to WebSocket for updates.",
        websocket_url=ws_url_placeholder
    )