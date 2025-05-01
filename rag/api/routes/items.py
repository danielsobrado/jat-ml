"""Item management routes."""
import logging

from fastapi import APIRouter, HTTPException, Depends

from rag.db.vector_store import vector_store
from rag.api.auth import conditional_auth, User
from rag.api.models import BatchAddRequest

logger = logging.getLogger("item_routes")

router = APIRouter(tags=["items"])

from pydantic import ValidationError

@router.post("/add_batch")
async def add_batch(request: dict):
    try:
        # Try to validate the request manually
        batch_request = BatchAddRequest(**request)
        
        # If validation passes, proceed
        count = vector_store.add_items(
            batch_request.collection_name,
            [item.dict() for item in batch_request.items]
        )
        
        return {
            "message": f"Successfully added {len(batch_request.items)} items to collection {batch_request.collection_name}",
            "count": len(batch_request.items)
        }
    except ValidationError as e:
        # Log the validation error details
        logger.error(f"Validation error: {e.json()}")
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        logger.error(f"Error adding batch: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding batch: {str(e)}")