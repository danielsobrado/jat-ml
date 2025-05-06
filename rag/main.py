from fastapi import FastAPI
import uvicorn
from loguru import logger
import os
import argparse

# Import the app from __init__.py
from . import app

# Configure logging
logger.add("rag_service.log", rotation="500 MB", level="INFO")

if __name__ == "__main__":
    logger.info("Starting RAG service...")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the RAG service")
    parser.add_argument("--server-port", type=int, default=8090, help="Port for the server")
    parser.add_argument("--server-host", type=str, default="0.0.0.0", help="Host for the server")
    args = parser.parse_args()
    
    try:
        # Get port from command line args or environment variable or default
        port = args.server_port
        host = args.server_host
        
        logger.info(f"Starting server on {host}:{port}")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Failed to start RAG service: {str(e)}")
        raise