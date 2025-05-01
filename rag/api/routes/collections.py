"""Collection management routes."""
import logging

from fastapi import APIRouter, HTTPException, Depends, Path

from rag.db.vector_store import vector_store
from rag.api.auth import conditional_auth, User
from rag.api.models import ListCollectionsResponse, CollectionInfo

logger = logging.getLogger("collection_routes")

router = APIRouter(tags=["collections"])

@router.get("/collections", response_model=ListCollectionsResponse)
async def list_collections():
    """List all available collections with their item counts."""
    try:
        collections = vector_store.list_collections()
        return {"collections": [CollectionInfo(**c) for c in collections]}
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing collections: {str(e)}")

@router.post("/collection/{collection_name}")
@conditional_auth
async def create_collection(
    collection_name: str = Path(..., description="Collection name"),
    current_user: User = None
):
    """Create a new empty collection."""
    try:
        vector_store.get_collection(collection_name)
        return {"message": f"Collection {collection_name} created successfully"}
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating collection: {str(e)}")

@router.delete("/collection/{collection_name}")
@conditional_auth
async def delete_collection(
    collection_name: str = Path(..., description="Collection name"),
    current_user: User = None
):
    """Delete a collection from ChromaDB."""
    try:
        if vector_store.delete_collection(collection_name):
            return {"message": f"Collection {collection_name} deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to delete collection {collection_name}")
    except Exception as e:
        logger.error(f"Error deleting collection: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting collection: {str(e)}")