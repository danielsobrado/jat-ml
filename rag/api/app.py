# rag/api/app.py
"""FastAPI application initialization."""
import logging
import asyncio # <--- Import asyncio
import time

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from rag.config import config
from rag.db.vector_store import vector_store
# Make the import explicit if not already done for clarity
from rag.db.postgres_reader import fetch_unspsc_commodities, engine as pg_engine # Import engine too
from rag.api.routes import auth, collections, items, search, rag_info
from rag.api.routes import chat as chat_router # ADDED: Import the new chat router
from rag.api.models import StatusResponse

logger = logging.getLogger("app")

# --- Startup Event Function (Combined Check & Populate) ---
async def startup_event():
    """Ensure required ChromaDB collections exist and populate UNSPSC if needed."""
    logger.info("Running startup tasks...")
    start_time_overall = time.time()

    # Get the current running event loop
    loop = asyncio.get_running_loop()

    # Allow some time for ChromaDB container to potentially start
    wait_time = 5 # seconds
    logger.info(f"Waiting {wait_time} seconds for ChromaDB service to potentially initialize...")
    await asyncio.sleep(wait_time) # asyncio.sleep is non-blocking

    # 1. Ensure ALL required collections exist (This part is usually fast, but could also be run in executor if needed)
    required_collections = [
        config.chromadb.manual_info_collection,
        config.chromadb.unspsc_collection,
        config.chromadb.common_collection
    ]
    logger.info(f"Ensuring ChromaDB collections exist: {required_collections}")
    collections_ok = True
    for col_name in required_collections:
        try:
            # vector_store.get_collection uses get_or_create, which might block briefly on creation.
            # For startup, this is often acceptable, but could be wrapped if creation is slow.
            await loop.run_in_executor(
                None, # Use default thread pool executor
                vector_store.get_collection, # The function to run
                col_name, # Arguments for the function
                True      # create_if_not_exists=True
            )
            logger.info(f"Collection '{col_name}' ensured.")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to get or create collection '{col_name}': {e}", exc_info=True)
            collections_ok = False

    if not collections_ok:
        logger.error("Aborting further startup tasks due to collection creation errors.")
        return

    # 2. Check and populate UNSPSC collection if empty
    unspsc_collection_name = config.chromadb.unspsc_collection
    logger.info(f"Checking population status for '{unspsc_collection_name}'...")
    try:
        # Get collection instance (should exist now)
        # Running get_collection again in executor for consistency
        unspsc_collection = await loop.run_in_executor(
            None, vector_store.get_collection, unspsc_collection_name, False
        )
        # count() might also be blocking
        count = await loop.run_in_executor(None, unspsc_collection.count)
        logger.info(f"Collection '{unspsc_collection_name}' current item count: {count}")

        if count == 0:
            logger.info(f"Collection '{unspsc_collection_name}' is empty. Attempting to populate from PostgreSQL...")
            populate_start_time = time.time()

            # Fetch data from PostgreSQL in a separate thread
            logger.info("Fetching UNSPSC data from PostgreSQL...")
            if pg_engine is None:
                 logger.error("PostgreSQL engine not initialized. Skipping population.")
                 unspsc_items = []
            else:
                # Wrap the synchronous fetch_unspsc_commodities in run_in_executor
                unspsc_items = await loop.run_in_executor(None, fetch_unspsc_commodities)
                logger.info(f"Fetched {len(unspsc_items)} UNSPSC commodities from PostgreSQL.")


            if not unspsc_items:
                logger.warning(f"No UNSPSC commodity items fetched. Collection '{unspsc_collection_name}' will remain empty.")
            else:
                logger.info(f"Preparing and adding {len(unspsc_items)} items in batches...")

                ids = [item["code"] for item in unspsc_items]
                documents = [item.get("description") or item.get("name", "") for item in unspsc_items]
                metadatas = [
                    {
                        "code": item["code"],
                        "name": item["name"],
                        "item_type": "unspsc_commodity"
                    } for item in unspsc_items
                ]

                batch_size = 500 # Adjust as needed
                added_count = 0
                total_batches = (len(ids) + batch_size - 1) // batch_size
                batch_start_time = time.time()

                for i in range(0, len(ids), batch_size):
                    batch_num = i // batch_size + 1
                    logger.info(f"Processing batch {batch_num}/{total_batches}...")
                    batch_ids = ids[i:i+batch_size]
                    batch_docs = documents[i:i+batch_size]
                    batch_metas = metadatas[i:i+batch_size]

                    try:
                        # --- Run the blocking ChromaDB add operation in a thread ---
                        await loop.run_in_executor(
                            None,         # Use default thread pool executor
                            lambda: unspsc_collection.add(  # Use lambda to pass named parameters
                                ids=batch_ids,
                                documents=batch_docs,
                                metadatas=batch_metas
                            )
                        )
                        # --- End run_in_executor ---

                        added_count += len(batch_ids)
                        current_time = time.time()
                        logger.info(f"Added batch {batch_num}/{total_batches} ({len(batch_ids)} items). Total added: {added_count}. Batch took: {current_time - batch_start_time:.2f}s")
                        batch_start_time = current_time # Reset timer for next batch

                        # Optional: yield control briefly between batches if needed
                        # await asyncio.sleep(0.01)

                    except Exception as batch_e:
                         logger.error(f"Error adding batch {batch_num} to '{unspsc_collection_name}': {batch_e}", exc_info=True)
                         logger.warning("Stopping population due to batch error.")
                         break

                # Final count might also block, run in executor
                final_count = await loop.run_in_executor(None, unspsc_collection.count)
                populate_duration = time.time() - populate_start_time
                logger.info(f"Finished populating '{unspsc_collection_name}'. Total items added: {added_count}, Final count: {final_count}, Duration: {populate_duration:.2f}s")
        else:
            logger.info(f"Collection '{unspsc_collection_name}' already contains data ({count} items). Skipping population.")

    except Exception as e:
        logger.error(f"Error during check/population of collection '{unspsc_collection_name}': {e}", exc_info=True)

    overall_duration = time.time() - start_time_overall
    logger.info(f"Startup tasks completed in {overall_duration:.2f} seconds.")


# (Keep the rest of create_app function as is)
# ...

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="RAG Classification Support API",
        description="API for storing and retrieving classification data and manual RAG information.",
        version="1.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add health check endpoint
    @app.get("/health")
    async def health_check():
        """Get API health status."""
        return {"status": "ok"}

    @app.get("/", response_model=StatusResponse, tags=["status"])
    async def get_status():
        """Get API status and information."""
        try:
            # Check ChromaDB connection (test_connection might block briefly)
            # Consider running it in executor too if it causes issues, but heartbeat is usually fast.
            chroma_connected = await asyncio.get_running_loop().run_in_executor(
                None, vector_store.test_connection
            )

            collections = []
            if chroma_connected:
                try:
                    # list_collections involves count() per collection, run in executor
                    collections_info = await asyncio.get_running_loop().run_in_executor(
                        None, vector_store.list_collections
                    )
                    collections = [c["name"] for c in collections_info]
                except Exception as e:
                    logger.error(f"Error listing collections during status check: {e}")

            return {
                "status": "ok",
                "chroma_connected": chroma_connected,
                "collections": collections,
                "auth_enabled": config.auth.enabled
            }
        except Exception as e:
            logger.error(f"Status check error: {e}", exc_info=True) # Log stack trace for status errors
            # Avoid raising 500 for status check unless critical, return unhealthy status maybe?
            # For now, keep raise as it indicates a problem getting status.
            raise HTTPException(status_code=500, detail=f"API status check error: {str(e)}")

    # Include routers
    app.include_router(auth.router)
    app.include_router(collections.router)
    app.include_router(items.router)
    app.include_router(search.router)
    app.include_router(
        rag_info.router,
        prefix="/v1/rag-info",
        tags=["RAG Information"]
    )
    app.include_router(chat_router.router) # ADDED: Include the chat router

    # Register Startup Event
    @app.on_event("startup")
    async def on_startup():
        # Run the startup event itself as a background task
        # This allows the server to start accepting requests *immediately*
        # while the potentially long-running population happens in the background.
        logger.info("Scheduling startup tasks (incl. potential population) to run in background.")
        asyncio.create_task(startup_event())
        # If you absolutely need population to finish *before* serving requests,
        # remove the create_task and just call await startup_event() here,
        # but accept that startup time will be longer.
        # await startup_event() # <--- Alternative: Blocks startup until finished

    logger.info(f"FastAPI app created. Auth enabled: {config.auth.enabled}")
    return app

# Create the FastAPI app instance
app = create_app()