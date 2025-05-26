"""ChromaDB vector store interaction."""
from http.client import HTTPException
import logging
import os
import requests
from typing import List, Dict, Any, Optional, Tuple
import time
from datetime import datetime, timezone

import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
from requests.exceptions import ConnectionError

from rag.config import config

# Use configured values
CHROMA_HOST = config.chromadb.host
CHROMA_PORT = config.chromadb.port
DEFAULT_COLLECTION = config.chromadb.default_collection
MANUAL_INFO_COLLECTION = config.chromadb.manual_info_collection

logger = logging.getLogger("vector_store")

# --- Metadata Keys ---
# Use constants for metadata field names for consistency and easier refactoring
META_TYPE = "item_type"       # To distinguish manual info from categories etc.
META_KEY = "original_key"    # Store the original key in metadata for filtering
META_CREATED_AT = "created_at_iso"
META_UPDATED_AT = "updated_at_iso"
TYPE_MANUAL = "manual_info"

class VectorStore:
    """ChromaDB vector store wrapper."""
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """Initialize ChromaDB client."""
        self.host = host or CHROMA_HOST
        self.port = port or CHROMA_PORT
        # Consider making embedding function configurable if needed
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        self.manual_info_collection_name = MANUAL_INFO_COLLECTION # Store configured name
        self.client = self._initialize_client()
        # Run migrations after client is fully initialized
        try:
            self._migrate_manual_info_metadata()
        except Exception as e:
            logger.error(f"Error during metadata migration: {e}")

    def _migrate_manual_info_metadata(self):
        """Migrates existing manual info items to ensure they have all required metadata fields."""
        collection = self._get_manual_info_collection()
        try:
            # Get all manual info items
            results = collection.get(
                where={META_TYPE: TYPE_MANUAL},
                include=['metadatas', 'documents']
            )
            
            if not results or not results.get('ids') or not results['ids']:
                logger.info("No manual info items found for metadata migration.")
                return
            
            updated_count = 0
            for i in range(len(results['ids'])):
                doc_id = results['ids'][i]
                document = results['documents'][i] if results.get('documents') and i < len(results['documents']) else ""
                metadata = results['metadatas'][i] if results.get('metadatas') and i < len(results['metadatas']) else {}
                
                # Check if name field is missing from metadata
                if 'name' not in metadata:
                    # Update metadata with name field
                    updated_metadata = metadata.copy()
                    updated_metadata['name'] = doc_id  # Use document ID (key) as name
                    
                    # Update the item
                    collection.update(
                        ids=[doc_id],
                        metadatas=[updated_metadata]
                    )
                    updated_count += 1
                    logger.info(f"Migrated metadata for item: {doc_id}, added name field")
            
            if updated_count > 0:
                logger.info(f"Migration completed: updated {updated_count} manual info items with name field")
            else:
                logger.info("No manual info items needed metadata migration.")
                
        except Exception as e:
            logger.error(f"Error during manual info metadata migration: {e}")

    def _initialize_client(self):
        """Initialize ChromaDB client."""
        try:
            self._check_server_availability()
            logger.info(f"Attempting to connect to ChromaDB HTTP Client at {self.host}:{self.port}")
            client = chromadb.HttpClient(
                host=self.host,
                port=self.port,
                # Explicitly specify tenant and database parameters
                tenant="default_tenant",
                database="default_database"
            )
            client.heartbeat() # Test connection
            logger.info("Successfully connected to ChromaDB server via HTTP.")
            
            return client
        except Exception as e:
            logger.warning(f"Failed to connect to ChromaDB server: {e}. Using persistent local client.")
            # Use a persistent directory instead of in-memory
            persist_dir = os.path.join("data", "chroma", "db")
            # Ensure directory exists
            os.makedirs(persist_dir, exist_ok=True)
            logger.info(f"Using persistent ChromaDB client with directory: {persist_dir}")
            # Create client with persistence
            client = chromadb.Client(Settings(persist_directory=persist_dir))
            
            return client

    def _check_server_availability(self, retries: int = 5, delay: int = 3, timeout: int = 5):
        """Check if ChromaDB server is available, with retries."""
        for attempt in range(retries):
            try:
                logger.info(f"Attempting to connect to ChromaDB server (attempt {attempt + 1}/{retries} at http://{self.host}:{self.port})...")
                response = requests.get(f"http://{self.host}:{self.port}/api/v1/heartbeat", timeout=timeout)
                response.raise_for_status()  # Raises error for bad status (4xx or 5xx)
                logger.info("ChromaDB server heartbeat check successful.")
                return True
            except requests.exceptions.RequestException as e: # Catch specific requests exceptions
                logger.warning(f"ChromaDB server heartbeat check attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    logger.info(f"Waiting {delay} seconds before next attempt...")
                    time.sleep(delay) # Ensure time module is imported (it is in the original file)
                else:
                    logger.error(f"All {retries} attempts to connect to ChromaDB server failed.")
                    # Raise ConnectionError to be caught by _initialize_client for fallback
                    raise ConnectionError(f"Cannot connect to ChromaDB at http://{self.host}:{self.port} after {retries} attempts") from e
        # This line should ideally not be reached if retries > 0, as ConnectionError would be raised.
        # However, to satisfy linters or strict type checking that expect a boolean return path:
        return False


    def test_connection(self) -> bool:
        """Test the connection to ChromaDB."""
        try:
            self.client.heartbeat()
            return True
        except Exception as e:
            logger.error(f"ChromaDB connection error: {e}")
            return False

    def _get_manual_info_collection(self):
        """Helper to get the specific collection for manual RAG info."""
        return self.client.get_or_create_collection(
            name=self.manual_info_collection_name,
            embedding_function=self.embedding_function
        )
    
    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections with their details."""
        collections = []
        try:
            for collection in self.client.list_collections():
                try:
                    col = self.client.get_collection(collection.name, embedding_function=self.embedding_function)
                    count = col.count()
                    collections.append({
                        "name": collection.name,
                        "count": count
                    })
                except Exception as e:
                    logger.warning(f"Error getting details for collection {collection.name}: {e}")
                    collections.append({
                        "name": collection.name,
                        "count": -1  # Error indicator
                    })
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
        return collections
    
    def get_collection(self, collection_name: str, create_if_not_exists: bool = True):
        """Get or create a collection."""
        try:
            # Always try get_or_create if create_if_not_exists is True
            if create_if_not_exists:
                 logger.info(f"Getting or creating collection: {collection_name}")
                 return self.client.get_or_create_collection(
                     name=collection_name,
                     embedding_function=self.embedding_function
                 )
            else:
                 # Only get if not creating
                 logger.info(f"Getting existing collection: {collection_name}")
                 return self.client.get_collection(
                     name=collection_name,
                     embedding_function=self.embedding_function
                 )
        except Exception as e:
             logger.error(f"Error accessing collection {collection_name}: {e}")
             raise # Re-raise the exception
    
    def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection.
        
        Args:
            collection_name: Name of the collection to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_collection(collection_name)
            return True
        except Exception as e:
            logger.error(f"Error deleting collection {collection_name}: {e}")
            return False
    
    def add_items(self, collection_name: str, items: List[Dict[str, Any]]) -> int:
        """Add items to a collection.
        
        Args:
            collection_name: Name of the collection
            items: List of items to add, each containing code, name, description, etc.
            
        Returns:
            Number of items added
        """
        collection = self.get_collection(collection_name)
        
        # Prepare data for ChromaDB
        ids = [item["code"] for item in items]
        documents = [item["description"] for item in items]
        metadatas = []
        
        for item in items:
            # Create metadata
            metadata = {
                "code": item["code"],
                "name": item["name"],
                "hierarchy": item.get("hierarchy", "")
            }
            # Add any additional metadata
            if "metadata" in item:
                metadata.update(item["metadata"])
            metadatas.append(metadata)
        
        # Add to ChromaDB
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        
        return len(items)
    
    def search(
        self,
        collection_name: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for similar items in a collection."""
        logger.info(f"Vector store searching for '{query}' in collection '{collection_name}' with limit {limit}")
        
        collection = self.get_collection(collection_name, create_if_not_exists=False) # Don't create on search

        results = collection.query(
            query_texts=[query],
            n_results=limit,
            include=['metadatas', 'documents', 'distances'] # Ensure necessary fields are included
        )

        formatted_results = []
        if results and results.get("ids") and results["ids"][0]: # Check if results are valid
             ids = results["ids"][0]
             metadatas = results.get("metadatas", [[]])[0]
             documents = results.get("documents", [[]])[0]
             distances = results.get("distances", [[]])[0]
             
             result_count = len(ids)
             logger.info(f"Vector store found {result_count} results for '{query}' in '{collection_name}'")

             for i in range(len(ids)):
                 metadata = metadatas[i] if i < len(metadatas) else {}
                 document = documents[i] if i < len(documents) else ""
                 
                 # Calculate similarity score (1 - distance) for cosine distance
                 # For L2 distance, similarity might need a different formula or just use distance
                 similarity = 0.0
                 if i < len(distances) and distances[i] is not None:
                    # Assuming default embedding function uses cosine distance where lower is better
                    similarity = 1.0 - distances[i]

                 formatted_results.append({
                     "code": ids[i], # ID is the code for categories
                     "name": metadata.get("name", ""),
                     "description": document,  # Include the actual document content as description
                     "hierarchy": metadata.get("hierarchy", ""),
                     "similarity_score": similarity,
                     "metadata": { # Exclude common fields from general metadata
                         k: v for k, v in metadata.items()
                         if k not in ["name", "hierarchy", "code"]
                     }
                 })
                 
                 # Log top 3 results with more detail
                 if i < 3:
                     doc_excerpt = document[:50] + "..." if document and len(document) > 50 else document
                     logger.debug(f"Result {i+1}: code={ids[i]}, name='{metadata.get('name', '')}', similarity={similarity:.3f}, document='{doc_excerpt}'")
                     
        else:
            logger.info(f"No results found for '{query}' in '{collection_name}'")
            
        return formatted_results
    
    def search_all_collections(
        self, 
        query: str, 
        limit_per_collection: int = 3,
        min_score: float = 0.0
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Search for similar items across all collections."""
        logger.info(f"Vector store searching all collections for query: '{query}', limit_per_collection: {limit_per_collection}, min_score: {min_score}")
        
        all_results = {}
        collections = self.client.list_collections()
        logger.info(f"Searching across {len(collections)} collections")
        
        for collection in collections:
            # Skip the manual info collection in this generic search
            if collection.name == self.manual_info_collection_name:
                continue
            try:
                logger.debug(f"Searching collection '{collection.name}' for '{query}'")
                results = self.search(
                    collection_name=collection.name,
                    query=query,
                    limit=limit_per_collection
                )
                
                # Filter by minimum score
                filtered_results = [r for r in results if r["similarity_score"] >= min_score]
                
                if filtered_results:
                    all_results[collection.name] = filtered_results
                    logger.info(f"Found {len(filtered_results)} results in '{collection.name}' for '{query}' (after min_score filtering)")
                else:
                    logger.info(f"No results with similarity >= {min_score} found in '{collection.name}' for '{query}'")
            except Exception as e:
                logger.warning(f"Error searching collection '{collection.name}' for '{query}': {e}")
                continue
        
        total_results_count = sum(len(results) for results in all_results.values())
        logger.info(f"Completed search_all_collections for '{query}'. Total results: {total_results_count} across {len(all_results)} collections")
        return all_results

    # --- New Methods for Manual RAG Info ---

    def add_manual_info(self, key: str, description: str) -> Dict[str, Any]:
        """Adds a manual information item to its specific collection."""
        collection = self._get_manual_info_collection()
        now_iso = datetime.now(timezone.utc).isoformat()

        metadata = {
            META_TYPE: TYPE_MANUAL,
            META_KEY: key, # Store original key in metadata too
            META_CREATED_AT: now_iso,
            META_UPDATED_AT: now_iso,
            "name": key,  # Add name field to metadata with key as value
        }
        doc_id = key # Use the key as the document ID

        try:
            collection.add(
                ids=[doc_id],
                documents=[description],
                metadatas=[metadata]
            )
            logger.info(f"Added manual info item with key: {key}, description: '{description[:50]}{'...' if len(description) > 50 else ''}'")
            return {
                "id": doc_id,
                "key": key,
                "description": description,
                "createdAt": now_iso,
                "updatedAt": now_iso
            }
        except Exception as e: # Catch potential duplicate ID errors etc.
             logger.error(f"Error adding manual info for key '{key}': {e}")
             # Re-raise or handle specific exceptions (like DuplicateIdError if library provides it)
             raise HTTPException(status_code=409, detail=f"Item with key '{key}' might already exist.") from e


    def get_manual_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Gets a manual information item by its key."""
        collection = self._get_manual_info_collection()
        try:
            result = collection.get(ids=[key], include=['metadatas', 'documents'])
            if not result or not result.get('ids') or not result['ids']:
                logger.warning(f"Manual info item not found for key: {key}")
                return None

            doc_id = result['ids'][0]
            document = result['documents'][0] if result.get('documents') else ""
            metadata = result['metadatas'][0] if result.get('metadatas') else {}

            # Verify it's the correct type
            if metadata.get(META_TYPE) != TYPE_MANUAL:
                 logger.warning(f"Retrieved item with key '{key}' but it's not of type '{TYPE_MANUAL}'")
                 return None


            return {
                "id": doc_id,
                "key": metadata.get(META_KEY, doc_id), # Prefer original key from metadata
                "description": document,
                "createdAt": metadata.get(META_CREATED_AT),
                "updatedAt": metadata.get(META_UPDATED_AT)
            }
        except Exception as e:
            logger.error(f"Error getting manual info for key '{key}': {e}")
            return None

    def update_manual_info(self, key: str, description: str) -> Optional[Dict[str, Any]]:
        """Updates the description of a manual information item."""
        collection = self._get_manual_info_collection()
        now_iso = datetime.now(timezone.utc).isoformat()

        # First, verify the item exists and get its current metadata
        existing_item = self.get_manual_info(key)
        if not existing_item:
            return None # Item not found

        # Prepare updated metadata
        updated_metadata = {
            META_TYPE: TYPE_MANUAL,
            META_KEY: key,
            META_CREATED_AT: existing_item.get("createdAt", now_iso), # Keep original creation time
            META_UPDATED_AT: now_iso,
            "name": key,  # Add name field to metadata with key as value
        }

        try:
            collection.update(
                ids=[key],
                documents=[description],
                metadatas=[updated_metadata]
            )
            logger.info(f"Updated manual info item with key: {key}, description: '{description[:50]}{'...' if len(description) > 50 else ''}'")
            return {
                "id": key,
                "key": key,
                "description": description,
                "createdAt": updated_metadata[META_CREATED_AT],
                "updatedAt": updated_metadata[META_UPDATED_AT]
            }
        except Exception as e:
            logger.error(f"Error updating manual info for key '{key}': {e}")
            return None # Indicate update failure

    def delete_manual_info(self, key: str) -> bool:
        """Deletes a manual information item by its key."""
        collection = self._get_manual_info_collection()
        try:
            # First get the item to log its description before deleting
            existing = self.get_manual_info(key)
            if not existing:
                logger.warning(f"Attempted to delete non-existent manual info item: {key}")
                return False

            collection.delete(ids=[key])
            logger.info(f"Deleted manual info item with key: {key}, description: '{existing['description'][:50]}{'...' if len(existing['description']) > 50 else ''}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting manual info for key '{key}': {e}")
            return False

    def list_manual_info(self, page: int = 1, limit: int = 10, search: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        """Lists manual information items with pagination and optional search."""
        collection = self._get_manual_info_collection()
        offset = (page - 1) * limit

        where_clause = {META_TYPE: TYPE_MANUAL}
        where_document_clause = None

        if search:
            # Simple search: check if search term is in key metadata OR description document
            # Note: This might be slow for large datasets without specific indexing.
            # Option 1: Search key metadata (exact match for now)
            # where_clause[META_KEY] = search
            # Option 2: Search document content
            where_document_clause = {"$contains": search}
            # Option 3: Combine? Could use $or in where_document if supported robustly
            # For now, let's prioritize document search for flexibility
            logger.debug(f"Applying search filter (in description): '{search}'")


        try:
            # First, get the total count matching the filter
            # Note: ChromaDB's count() doesn't directly support where_document.
            # We have to fetch all matching IDs/metadata first, then count. This isn't ideal for large datasets.
            # A more scalable approach might involve fetching only IDs/metadata and then counting.
            all_matching_items = collection.get(
                 where=where_clause,
                 where_document=where_document_clause,
                 include=[] # Don't need full data for count
            )
            total_count = len(all_matching_items['ids']) if all_matching_items and all_matching_items.get('ids') else 0
            logger.debug(f"Total count for manual info matching filter: {total_count}")


            # Then, get the paginated results
            results = collection.get(
                where=where_clause,
                where_document=where_document_clause, # Apply search filter here too
                limit=limit,
                offset=offset,
                include=['metadatas', 'documents']
            )

            items_data = []
            if results and results.get('ids') and results['ids']:
                for i in range(len(results['ids'])):
                    doc_id = results['ids'][i]
                    document = results['documents'][i] if results.get('documents') and i < len(results['documents']) else ""
                    metadata = results['metadatas'][i] if results.get('metadatas') and i < len(results['metadatas']) else {}

                    items_data.append({
                        "id": doc_id,
                        "key": metadata.get(META_KEY, doc_id),
                        "description": document,
                        "createdAt": metadata.get(META_CREATED_AT),
                        "updatedAt": metadata.get(META_UPDATED_AT)
                    })

            return items_data, total_count

        except Exception as e:
            logger.error(f"Error listing manual info: {e}")
            return [], 0

# Global vector store instance
vector_store = VectorStore()