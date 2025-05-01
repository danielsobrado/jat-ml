from fastapi import FastAPI
import uvicorn
from loguru import logger

# Import the app from __init__.py
from . import app

# Configure logging
logger.add("rag_service.log", rotation="500 MB", level="INFO")

if __name__ == "__main__":
    logger.info("Starting RAG service...")
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8080,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Failed to start RAG service: {str(e)}")
        raise