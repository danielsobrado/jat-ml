"""Search routes."""
import logging

from fastapi import APIRouter, HTTPException, Query

from rag.db.vector_store import vector_store
from rag.api.models import SimilarityResponse, SimilarityResult, MultiCollectionSearchResponse

logger = logging.getLogger("search_routes")

router = APIRouter(tags=["search"])

@router.get("/search", response_model=SimilarityResponse)
async def search_similar(
    query: str = Query(..., description="Description to search for"),
    collection_name: str = Query(..., description="Collection name"),
    limit: int = Query(5, description="Number of results to return")
):
    """Search for similar items in the specified ChromaDB collection."""
    logger.info(f"Received search request for query: '{query}' in collection: '{collection_name}', limit: {limit}")
    
    try:
        # Validate input
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        if not collection_name:
            raise HTTPException(status_code=400, detail="Collection name is required")
        
        # Get search results
        results = vector_store.search(
            collection_name=collection_name,
            query=query,
            limit=limit
        )
        
        # Log search results details
        result_count = len(results)
        logger.info(f"Search completed for '{query}' in '{collection_name}'. Found {result_count} results.")
        
        # Log a preview of top result if available
        if result_count > 0:
            top_result = results[0]
            # Include description in the log if it exists
            description = top_result.get('description', '')
            description_preview = f", description: '{description[:50]}{'...' if len(description) > 50 else ''}'" if description else ""
            logger.info(f"Top result for '{query}': code={top_result.get('code')}, name='{top_result.get('name')}', similarity={top_result.get('similarity_score', 0):.3f}{description_preview}")
        
        # Convert to API response model
        similarity_results = [SimilarityResult(**result) for result in results]
        
        return {
            "query": query,
            "collection_name": collection_name,
            "results": similarity_results
        }
    except Exception as e:
        logger.error(f"Search error for query '{query}' in collection '{collection_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

@router.get("/search_all", response_model=MultiCollectionSearchResponse)
async def search_across_collections(
    query: str = Query(..., description="Description to search for"),
    limit_per_collection: int = Query(3, description="Number of results per collection"),
    min_score: float = Query(0.0, description="Minimum similarity score (0-1)")
):
    """Search for similar items across all collections."""
    logger.info(f"Received search_all request for query: '{query}', limit_per_collection: {limit_per_collection}, min_score: {min_score}")
    
    try:
        # Validate input
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Get search results across all collections
        all_results = vector_store.search_all_collections(
            query=query,
            limit_per_collection=limit_per_collection,
            min_score=min_score
        )
        
        # Log results summary
        collection_counts = {coll: len(items) for coll, items in all_results.items()}
        total_items = sum(len(items) for items in all_results.values())
        logger.info(f"Search_all completed for '{query}'. Found {total_items} results across {len(all_results)} collections: {collection_counts}")
        
        # Log top result from each collection if available
        for coll_name, items in all_results.items():
            if items:
                top_result = items[0]
                logger.info(f"Top result in '{coll_name}' for '{query}': code={top_result.get('code')}, name='{top_result.get('name')}', similarity={top_result.get('similarity_score', 0):.3f}")
        
        # Convert to API response model
        formatted_results = {
            collection: [SimilarityResult(**item) for item in items]
            for collection, items in all_results.items()
        }
        
        return {
            "query": query,
            "results": formatted_results
        }
    except Exception as e:
        logger.error(f"Search_all error for query '{query}': {e}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")