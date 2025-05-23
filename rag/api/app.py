# rag/api/app.py (Modified)
"""FastAPI application initialization."""
import logging
import asyncio
import time

from fastapi import FastAPI, HTTPException, Depends # Keep existing FastAPI imports
from fastapi.middleware.cors import CORSMiddleware # Keep existing

from rag.config import config # Your existing config
from rag.db.vector_store import vector_store # Your existing vector_store
from rag.db.postgres_reader import fetch_unspsc_commodities, engine as pg_engine # Your existing db stuff
from rag.api.routes import auth, collections, items, search, rag_info # Your existing RAG API routes
from rag.api.models import StatusResponse 

# --- Import LangGraph Visualization Routers ---
from rag.langgraph_vis import api_routes as langgraph_api_router
# from rag.langgraph_vis import ws_handler as langgraph_ws_router # Commented out WebSocket router
from rag.langgraph_vis import sse_handler as langgraph_sse_router # NEW: Import SSE router

logger = logging.getLogger("app") # Assuming "app" is your root logger for this file

# --- Startup Event Function (Combined Check & Populate) ---
# Your existing startup_event function (ensure it's still relevant and works)
async def startup_event():
    """Ensure required ChromaDB collections exist and populate UNSPSC if needed."""
    logger.info("Running startup tasks...")
    start_time_overall = time.time()
    loop = asyncio.get_running_loop()
    wait_time = 5
    logger.info(f"Waiting {wait_time} seconds for ChromaDB service to potentially initialize...")
    await asyncio.sleep(wait_time)    
    required_collections = [
        config.chromadb.manual_info_collection,
        config.chromadb.unspsc_collection,
        config.chromadb.common_collection
    ]
    logger.info(f"Ensuring ChromaDB collections exist: {required_collections}")
    collections_ok = True
    for i, col_name in enumerate(required_collections):
        try:
            await loop.run_in_executor(None, vector_store.get_collection, col_name, True)
            logger.info(f"Collection '{col_name}' ensured.")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to get or create collection '{col_name}': {e}", exc_info=True)
            collections_ok = False
        # Yield control after each collection check to prevent blocking
        if i % 1 == 0:
            await asyncio.sleep(0)
    if not collections_ok:
        logger.error("Aborting further startup tasks due to collection creation errors.")
        return

    unspsc_collection_name = config.chromadb.unspsc_collection
    logger.info(f"Checking population status for '{unspsc_collection_name}'...")
    try:
        unspsc_collection = await loop.run_in_executor(None, vector_store.get_collection, unspsc_collection_name, False)
        count = await loop.run_in_executor(None, unspsc_collection.count)
        logger.info(f"Collection '{unspsc_collection_name}' current item count: {count}")
        if count == 0:
            logger.info(f"Collection '{unspsc_collection_name}' is empty. Attempting to populate from PostgreSQL...")
            populate_start_time = time.time()
            logger.info("Fetching UNSPSC data from PostgreSQL...")
            if pg_engine is None:
                 logger.error("PostgreSQL engine not initialized. Skipping population.")
                 unspsc_items = []
            else:
                unspsc_items = await loop.run_in_executor(None, fetch_unspsc_commodities)
                logger.info(f"Fetched {len(unspsc_items)} UNSPSC commodities from PostgreSQL.")

            if not unspsc_items:
                logger.warning(f"No UNSPSC commodity items fetched. Collection '{unspsc_collection_name}' will remain empty.")
            else:
                logger.info(f"Preparing and adding {len(unspsc_items)} items in batches...")
                ids = [item["code"] for item in unspsc_items]
                documents = [item.get("description") or item.get("name", "") for item in unspsc_items]
                metadatas = [{"code": item["code"], "name": item["name"], "item_type": "unspsc_commodity"} for item in unspsc_items]
                batch_size = 500
                added_count = 0
                total_batches = (len(ids) + batch_size - 1) // batch_size
                batch_start_time = time.time()
                for i in range(0, len(ids), batch_size):
                    batch_num = i // batch_size + 1
                    logger.info(f"Processing batch {batch_num}/{total_batches}...")
                    batch_ids, batch_docs, batch_metas = ids[i:i+batch_size], documents[i:i+batch_size], metadatas[i:i+batch_size]
                    try:
                        await loop.run_in_executor(None, lambda: unspsc_collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas))        # After populating each batch, yield control to let other tasks run
                        added_count += len(batch_ids)
                        current_time = time.time()
                        logger.info(f"Added batch {batch_num}/{total_batches} ({len(batch_ids)} items). Total added: {added_count}. Batch took: {current_time - batch_start_time:.2f}s")
                        batch_start_time = current_time
                        # Yield to the event loop periodically during large ingestions
                        if batch_num % 5 == 0:  # Every 5 batches
                            logger.debug(f"Yielding event loop during UNSPSC population after batch {batch_num}")
                            await asyncio.sleep(0)
                    except Exception as batch_e:
                         logger.error(f"Error adding batch {batch_num} to '{unspsc_collection_name}': {batch_e}", exc_info=True)
                         logger.warning("Stopping population due to batch error.")
                         break
                final_count = await loop.run_in_executor(None, unspsc_collection.count)
                populate_duration = time.time() - populate_start_time
                logger.info(f"Finished populating '{unspsc_collection_name}'. Total items added: {added_count}, Final count: {final_count}, Duration: {populate_duration:.2f}s")
        else:
            logger.info(f"Collection '{unspsc_collection_name}' already contains data ({count} items). Skipping population.")
    except Exception as e:
        logger.error(f"Error during check/population of collection '{unspsc_collection_name}': {e}", exc_info=True)
    overall_duration = time.time() - start_time_overall
    logger.info(f"Startup tasks completed in {overall_duration:.2f} seconds.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app_instance = FastAPI( # Renamed to app_instance to avoid conflict if 'app' is used globally later
        title="RAG Classification Support and LangGraph Visualization API", # MODIFIED title
        description="API for RAG, and visualizing/executing LangGraph workflows.", # MODIFIED description
        version="1.2.0", # MODIFIED version (example)
    )

    # Add CORS middleware (your existing setup)
    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add health check endpoint (your existing setup)
    @app_instance.get("/health")
    async def health_check():
        return {"status": "ok"}

    # Status endpoint (your existing setup, slightly adapted)
    @app_instance.get("/", response_model=StatusResponse, tags=["status"])
    async def get_status():
        try:
            chroma_connected = await asyncio.get_running_loop().run_in_executor(None, vector_store.test_connection)
            collections_list = [] # Renamed from 'collections' to avoid confusion
            if chroma_connected:
                try:
                    collections_info = await asyncio.get_running_loop().run_in_executor(None, vector_store.list_collections)
                    collections_list = [c["name"] for c in collections_info]
                except Exception as e:
                    logger.error(f"Error listing collections during status check: {e}")
            return {
                "status": "ok",
                "chroma_connected": chroma_connected,
                "collections": collections_list, # Ensure this matches StatusResponse model
                "auth_enabled": config.auth.enabled
            }
        except Exception as e:
            logger.error(f"Status check error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"API status check error: {str(e)}")

    # Include existing RAG routers
    app_instance.include_router(auth.router, prefix="/v1/auth", tags=["RAG Authentication"]) # Example: Add prefix for clarity
    app_instance.include_router(collections.router, prefix="/v1/rag", tags=["RAG Collections"])
    app_instance.include_router(items.router, prefix="/v1/rag", tags=["RAG Items"])
    app_instance.include_router(search.router, prefix="/v1/rag", tags=["RAG Search"])
    app_instance.include_router(rag_info.router, prefix="/v1/rag-info", tags=["RAG Information"]) # This one already had a prefix

    # --- NEW: Include LangGraph Visualization Routers ---
    # You might want a common prefix for all LangGraph visualization endpoints
    LG_VIS_PREFIX = "/v1/lg-vis"
    app_instance.include_router(langgraph_api_router.router, prefix=LG_VIS_PREFIX, tags=["LangGraph Management"])
    # app_instance.include_router(langgraph_ws_router.router, prefix=LG_VIS_PREFIX, tags=["LangGraph Execution (WS)"]) # WebSocket router
    app_instance.include_router(langgraph_sse_router.router, prefix=LG_VIS_PREFIX, tags=["LangGraph Execution (SSE)"]) # NEW: Include SSE router
    # Note: The WebSocket paths in ws_handler.py already include "/ws/langgraph/graphs/..."
    # If you add a prefix here like "/v1/lg-vis", the full WebSocket path would become, e.g.,
    # "/v1/lg-vis/ws/langgraph/graphs/{graph_id}/execute". Ensure client-side reflects this.
    # Alternatively, don't prefix the WebSocket router here if its paths are already absolute.
    # Given the paths in ws_handler.py, it's probably better NOT to prefix the ws_router here if those paths are intended to be root-relative.
    # Let's re-evaluate ws_router paths:
    # If ws_handler.py has paths like "/ws/langgraph/graphs/...", then including it with a prefix here
    # would result in "/v1/lg-vis/ws/langgraph/graphs/...".
    # Let's assume the paths in ws_handler.py are intended to be relative to the prefix IF the router is prefixed.
    # A common practice for WebSockets is to have them at a distinct root path.
    # I'll keep the prefix for now, meaning the full WS URL will be prefixed. Adjust if needed.
    # --- END NEW ---

    # Register Startup Event (your existing setup)
    @app_instance.on_event("startup")
    async def on_startup():
        logger.info("Scheduling startup tasks (incl. potential population) to run in background.")
        asyncio.create_task(startup_event())

    logger.info(f"FastAPI app created. Auth enabled: {config.auth.enabled}. LangGraph Vis modules included.")
    return app_instance

# Create the FastAPI app instance
app = create_app() # This is the 'app' your uvicorn main.py likely runs

# If your rag/main.py uses `from . import app` (referring to rag/__init__.py which exports rag.api.app:app),
# ensure that this 'app' variable is correctly exposed.