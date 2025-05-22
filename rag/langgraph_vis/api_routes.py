# rag/langgraph_vis/api_routes.py
import logging
import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Body, Depends, Path as FastAPIPath, Query
from fastapi.responses import JSONResponse

from .schemas import (
    GraphDefinition,
    GraphDefinitionListResponse,
    GraphDefinitionIdentifier,
    CreateGraphRequest,
    UpdateGraphRequest,
    ExecuteGraphRequest, 
    ExecuteGraphResponse, 
    MessageResponse,
    NodeDefinition,
    EdgeDefinition, # Added import
    ConditionalEdgesDefinition # Added import
)
from .core.builder import DynamicGraphBuilder, DynamicGraphBuilderError
# Import STATIC_GRAPHS_METADATA instead of just STATIC_GRAPHS
from .core.definitions import STATIC_GRAPHS, STATIC_GRAPHS_METADATA, STATE_SCHEMAS

from fastapi import Security 
async def get_current_active_user_placeholder():
    class DummyUser:
        username: str = "test_admin"
    return DummyUser()

logger = logging.getLogger(__name__)
router = APIRouter()

GRAPH_DEFINITIONS_DIR = Path(os.getenv("GRAPH_DEFINITIONS_DIR", "data/graph_definitions"))
GRAPH_DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Graph definitions will be stored in: {GRAPH_DEFINITIONS_DIR.resolve()}")

def _get_graph_definition_path(graph_id: str) -> Path:
    if ".." in graph_id or "/" in graph_id or "\\" in graph_id:
        raise ValueError("Invalid characters in graph_id.")
    return GRAPH_DEFINITIONS_DIR / f"{graph_id}.json"

def _load_graph_definition_from_file(graph_id: str) -> GraphDefinition | None:
    file_path = _get_graph_definition_path(graph_id)
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            return GraphDefinition(**data)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON for graph ID '{graph_id}' from {file_path}")
            return None
        except Exception as e: 
            logger.error(f"Error loading/validating graph definition for graph ID '{graph_id}': {e}")
            return None
    return None

def _save_graph_definition_to_file(graph_def: GraphDefinition) -> None:
    file_path = _get_graph_definition_path(graph_def.id)
    try:
        with open(file_path, "w") as f:
            json.dump(graph_def.model_dump(mode="json"), f, indent=2)
        logger.info(f"Saved graph definition '{graph_def.name}' (ID: {graph_def.id}) to {file_path}")
    except Exception as e:
        logger.error(f"Error saving graph definition ID '{graph_def.id}' to {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save graph definition: {str(e)}")

def _delete_graph_definition_file(graph_id: str) -> bool:
    file_path = _get_graph_definition_path(graph_id)
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"Deleted graph definition file for ID '{graph_id}': {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting graph definition file for ID '{graph_id}': {e}")
            return False
    return False 

@router.post(
    "/graphs",
    response_model=GraphDefinition,
    status_code=201,
    summary="Create a new graph definition",
    dependencies=[Depends(get_current_active_user_placeholder)] 
)
async def create_graph_definition(
    graph_create_request: CreateGraphRequest = Body(...)
):
    logger.info(f"Received request to create graph: {graph_create_request.name}")
    graph_def = GraphDefinition(**graph_create_request.model_dump())
    try:
        DynamicGraphBuilder(graph_def).build() 
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
    saved_graphs: List[GraphDefinitionIdentifier] = []
    for file_path in GRAPH_DEFINITIONS_DIR.glob("*.json"):
        graph_id = file_path.stem
        graph_def = _load_graph_definition_from_file(graph_id)
        if graph_def:
            saved_graphs.append(
                GraphDefinitionIdentifier(id=graph_def.id, name=graph_def.name, updated_at=graph_def.updated_at)
            )
    
    if include_static:
        for name, meta_data in STATIC_GRAPHS_METADATA.items():
            static_graph_id = f"static_{name}"
            if not any(g.id == static_graph_id for g in saved_graphs):
                compiled_graph = meta_data["compiled_graph"]
                updated_at_static = compiled_graph.compiled_at if hasattr(compiled_graph, 'compiled_at') else datetime.utcnow()
                saved_graphs.append(
                    GraphDefinitionIdentifier(
                        id=static_graph_id,
                        name=f"[STATIC] {name.replace('_', ' ').title()}",
                        updated_at=updated_at_static
                    )
                )
    return GraphDefinitionListResponse(graphs=saved_graphs)

@router.get(
    "/graphs/{graph_id}",
    response_model=GraphDefinition, 
    summary="Get a specific graph definition"
)
async def get_graph_definition(
    graph_id: str = FastAPIPath(..., description="The ID of the graph definition to retrieve.")
):
    logger.debug(f"Request to get graph definition for ID: {graph_id}")
    
    if graph_id.startswith("static_"):
        static_graph_name = graph_id[len("static_"):]
        if static_graph_name in STATIC_GRAPHS_METADATA:
            logger.info(f"Constructing GraphDefinition for static graph: {static_graph_name}")
            metadata = STATIC_GRAPHS_METADATA[static_graph_name]
            compiled_graph = metadata["compiled_graph"] # Keep for compiled_at if needed

            # Use the predefined structure from metadata
            return GraphDefinition(
                id=graph_id,
                name=f"[STATIC] {static_graph_name.replace('_', ' ').title()}",
                description=metadata.get("description", f"Static graph: {static_graph_name}"),
                state_schema_name=metadata["state_schema_name"],
                nodes=metadata.get("nodes", []), # Use predefined nodes
                edges=metadata.get("edges", []), # Use predefined edges
                conditional_edges=metadata.get("conditional_edges", []), # Use predefined conditional_edges
                entry_point_node_id=metadata["entry_point_node_id"],
                terminal_node_ids=metadata.get("terminal_node_ids", []), # Use predefined terminal_node_ids
                created_at=compiled_graph.compiled_at if hasattr(compiled_graph, 'compiled_at') else datetime.utcnow(),
                updated_at=compiled_graph.compiled_at if hasattr(compiled_graph, 'compiled_at') else datetime.utcnow(),
                version=1 # Default version for static
            )
        else:
            raise HTTPException(status_code=404, detail=f"Static graph with name '{static_graph_name}' not found.")

    graph_def = _load_graph_definition_from_file(graph_id)
    if not graph_def:
        raise HTTPException(status_code=404, detail=f"Graph definition with ID '{graph_id}' not found.")
    return graph_def

@router.put(
    "/graphs/{graph_id}",
    response_model=GraphDefinition,
    summary="Update an existing graph definition",
    dependencies=[Depends(get_current_active_user_placeholder)] 
)
async def update_graph_definition(
    graph_id: str = FastAPIPath(..., description="The ID of the graph definition to update."),
    graph_update_request: UpdateGraphRequest = Body(...)
):
    logger.info(f"Received request to update graph ID: {graph_id}")
    existing_graph_def = _load_graph_definition_from_file(graph_id)
    if not existing_graph_def:
        raise HTTPException(status_code=404, detail=f"Graph definition with ID '{graph_id}' not found for update.")

    updated_graph_data = graph_update_request.model_dump()
    updated_graph_data["id"] = existing_graph_def.id 
    updated_graph_data["created_at"] = existing_graph_def.created_at 
    updated_graph_data["updated_at"] = datetime.utcnow() 

    updated_graph_def = GraphDefinition(**updated_graph_data)
    # updated_graph_def.updated_at = updated_graph_def.model_fields['updated_at'].default_factory() # Pydantic v2 style

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
    status_code=200, 
    summary="Delete a graph definition",
    dependencies=[Depends(get_current_active_user_placeholder)]
)
async def delete_graph_definition(
    graph_id: str = FastAPIPath(..., description="The ID of the graph definition to delete.")
):
    logger.info(f"Request to delete graph definition ID: {graph_id}")
    if graph_id.startswith("static_"):
        raise HTTPException(status_code=400, detail="Static graph definitions cannot be deleted via this API.")

    if not _delete_graph_definition_file(graph_id):
        if _get_graph_definition_path(graph_id).exists(): 
             raise HTTPException(status_code=500, detail=f"Failed to delete graph definition file for ID '{graph_id}'.")
        raise HTTPException(status_code=404, detail=f"Graph definition with ID '{graph_id}' not found.")
    
    return MessageResponse(message=f"Graph definition with ID '{graph_id}' deleted successfully.")

@router.post(
    "/graphs/{graph_id}/execute",
    response_model=ExecuteGraphResponse,
    summary="Trigger execution of a graph (non-streaming)",
    dependencies=[Depends(get_current_active_user_placeholder)] 
)
async def execute_graph_http(
    graph_id: str = FastAPIPath(..., description="ID of the graph to execute (saved or static)."),
    fastapi_req: ExecuteGraphRequest = Body(...), # Renamed to avoid conflict with Starlette Request
):
    logger.info(f"HTTP request to execute graph ID: {graph_id} with inputs: {fastapi_req.input_args}")
    
    compiled_graph = None
    if graph_id.startswith("static_"):
        static_graph_name = graph_id[len("static_"):]
        if static_graph_name in STATIC_GRAPHS_METADATA:
            compiled_graph = STATIC_GRAPHS_METADATA[static_graph_name]["compiled_graph"]
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

    if not compiled_graph: 
        raise HTTPException(status_code=500, detail=f"Could not load or build graph '{graph_id}'.")

    execution_id = f"exec_{os.urandom(8).hex()}" 
    
    # This path is relative to the LG_VIS_PREFIX defined in app.py
    # If LG_VIS_PREFIX = "/v1/lg-vis", then this will be correct.
    ws_path = router.url_path_for("websocket_execute_graph_with_id", graph_id=graph_id, execution_id=execution_id)
    # The full URL will depend on the request's base URL, which FastAPI can't know directly here easily.
    # Client usually constructs this from relative path or a configured base WS URL.
    # For now, just returning the path.

    logger.info(f"Generated execution ID '{execution_id}' for graph '{graph_id}'. Client should connect to WebSocket at path: {ws_path}")

    return ExecuteGraphResponse(
        execution_id=execution_id,
        message=f"Graph execution '{execution_id}' initiated for graph '{graph_id}'. Connect to WebSocket for updates.",
        websocket_url=str(ws_path) # Return the path
    )