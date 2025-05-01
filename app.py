"""
Entry point for the RAG service application.
Simplifies importing the FastAPI app for uvicorn.
"""
# Import from the actual module structure
from rag.api.app import app

# This file allows simpler imports, so you can run:
# uvicorn app:app --reload

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get host and port from environment variables or use defaults
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8090"))
    
    # Start the server directly
    uvicorn.run("app:app", host=host, port=port, reload=True)