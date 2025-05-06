"""Configuration loader for the application."""
import os
import yaml
from typing import Dict, Any, Optional
import logging
from dataclasses import dataclass, field # Import field

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("config")

@dataclass
class ServerConfig:
    host: str
    port: int
    log_level: str
    environment: str

@dataclass
class ChromaDBConfig:
    host: str
    port: int
    default_collection: str
    manual_info_collection: str 
    unspsc_collection: str
    common_collection: str
@dataclass
class PostgreSQLConfig:
    host: str
    port: int
    user: str
    password: str
    dbname: str

@dataclass
class AuthConfig:
    enabled: bool
    secret_key: str
    token_expire_minutes: int
    default_admin: Dict[str, str]

@dataclass
class AppConfig:
    server: ServerConfig
    chromadb: ChromaDBConfig
    auth: AuthConfig
    postgres: PostgreSQLConfig 

def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from YAML file and environment variables.
    
    Args:
        config_path: Path to YAML config file (optional, defaults to config.yaml in cwd)
        
    Returns:
        AppConfig: Application configuration
    """
    # Default config file path
    if config_path is None:
        config_path = os.environ.get("CONFIG_PATH", "config.yaml") # Look for config.yaml relative to where script is run
    
    logger.info(f"Attempting to load configuration from: {config_path}")

    # Load config from YAML
    config_data = {}
    try:
        # Try absolute path first
        abs_config_path = os.path.abspath(config_path)
        logger.debug(f"Absolute config path: {abs_config_path}")
        with open(abs_config_path, "r") as f:
            config_data = yaml.safe_load(f)
            logger.info(f"Successfully loaded config from absolute path: {abs_config_path}")
    except FileNotFoundError:
         logger.warning(f"Config file not found at absolute path {abs_config_path}. Trying relative path {config_path}")
         try:
              with open(config_path, "r") as f:
                  config_data = yaml.safe_load(f)
                  logger.info(f"Successfully loaded config from relative path: {config_path}")
         except FileNotFoundError:
              logger.warning(f"Config file not found at {config_path}. Using default values and environment variables.")
         except Exception as e:
              logger.error(f"Error loading config file from relative path {config_path}: {e}")
    except Exception as e:
        logger.error(f"Error loading config file from absolute path {abs_config_path}: {e}")

    if not isinstance(config_data, dict): # Handle empty or invalid YAML
        logger.warning(f"Config data loaded from {config_path} is not a dictionary or is empty. Relying on defaults/env vars.")
        config_data = {}


    # Server config with environment variable overrides
    server_config_yaml = config_data.get("server", {})
    server = ServerConfig(
        host=os.environ.get("SERVER_HOST", server_config_yaml.get("host", "0.0.0.0")),
        port=int(os.environ.get("SERVER_PORT", server_config_yaml.get("port", 8080))),
        log_level=os.environ.get("LOG_LEVEL", server_config_yaml.get("log_level", "INFO")).upper(),
        environment=os.environ.get("ENVIRONMENT", server_config_yaml.get("environment", "production"))
    )
    
    # ChromaDB config with environment variable overrides
    chromadb_config_yaml = config_data.get("chromadb", {})
    chromadb = ChromaDBConfig(
        host=os.environ.get("CHROMA_HOST", chromadb_config_yaml.get("host", "localhost")),
        port=int(os.environ.get("CHROMA_PORT", chromadb_config_yaml.get("port", 8000))),
        default_collection=os.environ.get(
            "DEFAULT_COLLECTION", 
            chromadb_config_yaml.get("default_collection", "unspsc_categories")
        ),
        # Add manual_info_collection loading
        manual_info_collection=os.environ.get(
            "MANUAL_INFO_COLLECTION",
            chromadb_config_yaml.get("manual_info_collection", "rag_manual_info") # Default name
        ),
        # Add unspsc_collection and common_collection loading
        unspsc_collection=os.environ.get(
            "UNSPSC_COLLECTION",
            chromadb_config_yaml.get("unspsc_collection", "unspsc_categories")
        ),
        common_collection=os.environ.get(
            "COMMON_COLLECTION",
            chromadb_config_yaml.get("common_collection", "common_categories")
        )
    )
    
    # Auth config with environment variable overrides
    auth_config_yaml = config_data.get("auth", {})
    default_admin_yaml = auth_config_yaml.get("default_admin", {})
    auth = AuthConfig(
        enabled=os.environ.get("ENABLE_AUTH", str(auth_config_yaml.get("enabled", True))).lower() == "true",
        secret_key=os.environ.get("SECRET_KEY", auth_config_yaml.get("secret_key", "CHANGE_THIS_TO_A_SECURE_SECRET")),
        token_expire_minutes=int(os.environ.get(
            "ACCESS_TOKEN_EXPIRE_MINUTES", 
            auth_config_yaml.get("token_expire_minutes", 30)
        )),
        default_admin={
            "username": os.environ.get("ADMIN_USERNAME", default_admin_yaml.get("username", "admin")),
            "password": os.environ.get("ADMIN_PASSWORD", default_admin_yaml.get("password", "admin"))
        }
    )
    
    # PostgreSQL config with environment variable overrides
    postgres_config_yaml = config_data.get("postgres", {})
    postgres = PostgreSQLConfig(
        host=os.environ.get("PG_HOST", postgres_config_yaml.get("host", "localhost")),
        port=int(os.environ.get("PG_PORT", postgres_config_yaml.get("port", 5433))),
        user=os.environ.get("PG_USER", postgres_config_yaml.get("user", "unspsc")),
        password=os.environ.get("PG_PASSWORD", postgres_config_yaml.get("password", "unspsc")),
        dbname=os.environ.get("PG_DBNAME", postgres_config_yaml.get("dbname", "unspsc"))
    )
    
    # Log loaded config (mask sensitive info if needed)
    logger.info("Configuration Loaded:")
    logger.info(f"  Server: host={server.host}, port={server.port}, log_level={server.log_level}, env={server.environment}")
    logger.info(f"  ChromaDB: host={chromadb.host}, port={chromadb.port}, default_collection='{chromadb.default_collection}', manual_info_collection='{chromadb.manual_info_collection}', unspsc_collection='{chromadb.unspsc_collection}', common_collection='{chromadb.common_collection}'")
    logger.info(f"  PostgreSQL: host={postgres.host}, port={postgres.port}, user='{postgres.user}', dbname='{postgres.dbname}'")
    logger.info(f"  Auth: enabled={auth.enabled}, token_expire={auth.token_expire_minutes}m, admin_user='{auth.default_admin['username']}'")
    if not auth.secret_key or auth.secret_key == "CHANGE_THIS_TO_A_SECURE_SECRET":
         logger.warning("Security warning: Using default or missing SECRET_KEY. Please set a strong secret key in config or environment variable.")

    return AppConfig(server=server, chromadb=chromadb, auth=auth, postgres=postgres)

# Global config instance
config = load_config()

def get_server_settings(self) -> ServerConfig:
    """Get server settings from configuration"""
    server_config_yaml = self.config_yaml.get("server", {})
    
    return ServerConfig(
        host=server_config_yaml.get("host", "0.0.0.0"),
        port=int(os.environ.get("SERVER_PORT", server_config_yaml.get("port", 8090))),
        environment=server_config_yaml.get("environment", "production"),
        log_level=server_config_yaml.get("log_level", "INFO"),
    )