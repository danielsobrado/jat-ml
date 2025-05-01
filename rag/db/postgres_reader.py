# rag/db/postgres_reader.py
import logging
from typing import List, Dict, Any
from sqlalchemy import create_engine, text

from rag.config import config # Import the global config

logger = logging.getLogger("postgres_reader")

DATABASE_URL = f"postgresql+psycopg2://{config.postgres.user}:{config.postgres.password}@{config.postgres.host}:{config.postgres.port}/{config.postgres.dbname}"

try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    logger.info(f"SQLAlchemy engine created for {config.postgres.host}:{config.postgres.port}/{config.postgres.dbname}")
except Exception as e:
    logger.error(f"Failed to create SQLAlchemy engine: {e}", exc_info=True)
    engine = None # Set engine to None if creation fails

def fetch_unspsc_commodities() -> List[Dict[str, Any]]:
    """Fetches UNSPSC Commodity level categories from the PostgreSQL database."""
    if engine is None:
        logger.error("Database engine not initialized. Cannot fetch UNSPSC commodities.")
        return []

    # Find the system ID for UNSPSC
    system_id_query = text("SELECT id FROM classification_systems WHERE code = 'UNSPSC' LIMIT 1")
    # Find the level code for Commodity (assuming it's level 4 and code 'commodity')
    commodity_level_code = 'commodity' # Assuming this is the code stored in classification_levels

    items = []
    try:
        with engine.connect() as connection:
            logger.info("Fetching UNSPSC System ID...")
            result = connection.execute(system_id_query)
            system_id_row = result.fetchone()
            if not system_id_row:
                logger.error("UNSPSC system not found in classification_systems table.")
                return []
            unspsc_system_id = system_id_row[0]
            logger.info(f"Found UNSPSC System ID: {unspsc_system_id}")

            # Fetch commodities for the UNSPSC system
            commodity_query = text(f"""
                SELECT code, name, description
                FROM categories
                WHERE system_id = :system_id AND level_code = :level_code
            """)
            logger.info(f"Fetching categories for system_id={unspsc_system_id}, level_code='{commodity_level_code}'...")
            result = connection.execute(commodity_query, {"system_id": unspsc_system_id, "level_code": commodity_level_code})

            for row in result:
                items.append({
                    "code": row[0],
                    "name": row[1],
                    "description": row[2] if row[2] else row[1] # Use name if description is null
                })
            logger.info(f"Fetched {len(items)} UNSPSC commodity categories.")

    except Exception as e:
        logger.error(f"Error fetching UNSPSC commodities from PostgreSQL: {e}", exc_info=True)
        return [] # Return empty list on error

    return items