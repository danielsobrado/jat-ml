# rag/api/routes/rag_info.py
"""Routes for managing manual RAG information."""
import logging
import math
from datetime import datetime, timezone
from typing import Optional # Import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body, status

# Assuming vector_store is correctly initialized in rag/db/vector_store.py
from rag.db.vector_store import vector_store
# Assuming auth utilities are correctly defined
from rag.api.auth import User, get_current_active_user
from rag.api.models import (
    RagInfoItem,
    RagInfoItemCreate,
    RagInfoItemUpdate,
    RagInfoPageResponse # Use the correct Pydantic model for the list response
)
# Assuming config is correctly loaded
from rag.config import config

logger = logging.getLogger("rag_info_routes")

# Define a placeholder dependency that does nothing when auth is disabled
# It MUST be an async function if the real dependency is also async
async def get_no_auth_dependency() -> None:
    return None

# REMOVED prefix from router definition
router = APIRouter(tags=["RAG Information"])

DEFAULT_PAGE_SIZE = 10 # Consistent page size

@router.get(
    "",
    response_model=RagInfoPageResponse, # Use the correct response model
    summary="List RAG Information Items",
    description="Retrieves a paginated list of manually added RAG information items, with optional search.",
)
async def list_rag_info(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search term for key or description"),
    _user: Optional[User] = Depends(get_current_active_user if config.auth.enabled else get_no_auth_dependency)
):
    """
    Lists manually added RAG information entries with pagination and search.
    Matches the GET /v1/rag-info endpoint expected by the Go client.
    """
    logger.info(f"Listing RAG info: page={page}, limit={limit}, search='{search or ''}'")
    try:
        # vector_store.list_manual_info returns a tuple: (list_of_dicts, total_count)
        items_data, total_count = vector_store.list_manual_info(page=page, limit=limit, search=search)

        items_list = []
        for item_dict in items_data:
             try:
                 # Attempt to parse dates, provide defaults if missing/invalid
                 # Chroma metadata values are often strings, ensure robust parsing
                 created_at_str = item_dict.get('createdAt')
                 updated_at_str = item_dict.get('updatedAt')

                 created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(timezone.utc)
                 updated_at = datetime.fromisoformat(updated_at_str) if updated_at_str else datetime.now(timezone.utc)

                 items_list.append(RagInfoItem(
                     id=str(item_dict.get('id', 'N/A')), # Ensure ID is string
                     key=str(item_dict.get('key', 'N/A')), # Ensure key is string
                     description=str(item_dict.get('description', '')),
                     createdAt=created_at,
                     updatedAt=updated_at
                 ))
             except (ValueError, TypeError) as date_err:
                  logger.warning(f"Could not parse date for item {item_dict.get('id')}: {date_err}. Using current time.")
                  # Append with current time as fallback, ensure types match model
                  items_list.append(RagInfoItem(
                     id=str(item_dict.get('id', 'parse_error_id')),
                     key=str(item_dict.get('key', 'parse_error_key')),
                     description=str(item_dict.get('description', '')),
                     createdAt=datetime.now(timezone.utc),
                     updatedAt=datetime.now(timezone.utc)
                  ))

        total_pages = math.ceil(total_count / limit) if limit > 0 else 1

        return RagInfoPageResponse(
            items=items_list,
            totalCount=total_count,
            totalPages=total_pages,
            currentPage=page
        )
    except Exception as e:
        logger.error(f"Error listing RAG info: {e}", exc_info=True) # Log stack trace
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve RAG information list."
        )

@router.post(
    "",
    response_model=RagInfoItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create RAG Information Item",
    description="Adds a new key-value information item to the RAG store.",
)
async def create_rag_info(
    item_in: RagInfoItemCreate,
    _user: Optional[User] = Depends(get_current_active_user if config.auth.enabled else get_no_auth_dependency)
):
    """
    Creates a new manual RAG information entry.
    Matches the POST /v1/rag-info endpoint.
    """
    user_info = _user.username if config.auth.enabled and _user else 'anonymous'
    logger.info(f"User '{user_info}' creating RAG info item with key: {item_in.key}, description: '{item_in.description[:50]}{'...' if len(item_in.description) > 50 else ''}'")
    try:
        # vector_store.add_manual_info should return a dict matching RagInfoItem structure
        created_item_dict = vector_store.add_manual_info(key=item_in.key, description=item_in.description)

        # Parse dates from the returned dict
        created_at = datetime.fromisoformat(created_item_dict.get('createdAt'))
        updated_at = datetime.fromisoformat(created_item_dict.get('updatedAt'))

        return RagInfoItem(
             id=str(created_item_dict.get('id')),
             key=str(created_item_dict.get('key')),
             description=str(created_item_dict.get('description')),
             createdAt=created_at,
             updatedAt=updated_at
         )
    except HTTPException as http_exc: # Catch potential 409 from vector store add
         logger.warning(f"HTTP Exception during RAG info creation for key '{item_in.key}': {http_exc.detail}")
         raise http_exc
    except Exception as e:
        logger.error(f"Error creating RAG info for key '{item_in.key}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create RAG information item."
        )

@router.get(
    "/{item_id}",
    response_model=RagInfoItem,
    summary="Get RAG Information Item",
    description="Retrieves a specific RAG information item by its key (ID).",
)
async def get_rag_info(
    item_id: str = Path(..., description="The key/ID of the RAG info item to retrieve"),
    _user: Optional[User] = Depends(get_current_active_user if config.auth.enabled else get_no_auth_dependency)
):
    """
    Retrieves a specific manual RAG information item by its key.
    Matches the GET /v1/rag-info/{id} endpoint.
    """
    logger.debug(f"Attempting to retrieve RAG info item with key: {item_id}")
    try:
        item_dict = vector_store.get_manual_info(key=item_id)
        if item_dict is None:
            logger.warning(f"RAG info item not found: {item_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RAG info item not found")

        # Parse dates
        created_at_str = item_dict.get('createdAt')
        updated_at_str = item_dict.get('updatedAt')
        created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(timezone.utc)
        updated_at = datetime.fromisoformat(updated_at_str) if updated_at_str else datetime.now(timezone.utc)

        return RagInfoItem(
            id=str(item_dict.get('id')),
            key=str(item_dict.get('key')),
            description=str(item_dict.get('description')),
            createdAt=created_at,
            updatedAt=updated_at
        )
    except HTTPException:
         raise # Re-raise HTTP 404
    except (ValueError, TypeError) as date_err:
        logger.error(f"Error parsing date for RAG info item '{item_id}': {date_err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to parse date format for the item.")
    except Exception as e:
        logger.error(f"Error retrieving RAG info for key '{item_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve RAG information item."
        )

@router.put(
    "/{item_id}",
    response_model=RagInfoItem,
    summary="Update RAG Information Item",
    description="Updates the description of an existing RAG information item.",
)
async def update_rag_info(
    item_id: str = Path(..., description="The key/ID of the item to update"),
    item_update: RagInfoItemUpdate = Body(...),
    _user: Optional[User] = Depends(get_current_active_user if config.auth.enabled else get_no_auth_dependency)
):
    """
    Updates the description of a specific manual RAG information item.
    Matches the PUT /v1/rag-info/{id} endpoint.
    """
    user_info = _user.username if config.auth.enabled and _user else 'anonymous'
    logger.info(f"User '{user_info}' updating RAG info item: {item_id}, description: '{item_update.description[:50]}{'...' if len(item_update.description) > 50 else ''}'")
    try:
        # vector_store.update_manual_info should return a dict or None
        updated_item_dict = vector_store.update_manual_info(key=item_id, description=item_update.description)
        if updated_item_dict is None:
            logger.warning(f"Attempted to update non-existent RAG info item: {item_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RAG info item not found")

        # Parse dates
        created_at_str = updated_item_dict.get('createdAt')
        updated_at_str = updated_item_dict.get('updatedAt')
        created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(timezone.utc)
        updated_at = datetime.fromisoformat(updated_at_str) if updated_at_str else datetime.now(timezone.utc)

        return RagInfoItem(
            id=str(updated_item_dict.get('id')),
            key=str(updated_item_dict.get('key')),
            description=str(updated_item_dict.get('description')),
            createdAt=created_at,
            updatedAt=updated_at
        )
    except HTTPException:
         raise # Re-raise HTTP 404
    except (ValueError, TypeError) as date_err:
        logger.error(f"Error parsing date for updated RAG info item '{item_id}': {date_err}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to parse date format for the updated item.")
    except Exception as e:
        logger.error(f"Error updating RAG info for key '{item_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update RAG information item."
        )

@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete RAG Information Item",
    description="Deletes a specific RAG information item by its key (ID).",
)
async def delete_rag_info(
    item_id: str = Path(..., description="The key/ID of the item to delete"),
    _user: Optional[User] = Depends(get_current_active_user if config.auth.enabled else get_no_auth_dependency)
):
    """
    Deletes a specific manual RAG information item by its key.
    Matches the DELETE /v1/rag-info/{id} endpoint.
    """
    user_info = _user.username if config.auth.enabled and _user else 'anonymous'
    logger.info(f"User '{user_info}' deleting RAG info item: {item_id}")
    try:
        # vector_store.delete_manual_info returns bool
        deleted = vector_store.delete_manual_info(key=item_id)
        if not deleted:
            # To provide accurate 404, check if it existed right before trying to delete
            # (There's a small race condition window here, but generally okay)
            if vector_store.get_manual_info(key=item_id) is None:
                 logger.warning(f"Attempted to delete RAG info item that was not found: {item_id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RAG info item not found")
            else:
                 # If it exists but delete failed, it's likely an internal error
                 logger.error(f"Delete operation failed unexpectedly for RAG info item: {item_id}")
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete RAG information item.")
        # If deleted is True, FastAPI automatically returns 204 No Content
        return None
    except HTTPException:
        raise # Re-raise HTTP 404 or others
    except Exception as e:
        logger.error(f"Error deleting RAG info for key '{item_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete RAG information item."
        )