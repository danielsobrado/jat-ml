# RAG Classification Support API

A modular and secure API using FastAPI for managing classification data (like UNSPSC) and supporting Retrieval-Augmented Generation (RAG) workflows. It leverages ChromaDB for vector storage/search and PostgreSQL for relational data.

## Project Structure

```
unspsc-classifier/
├── .vscode/                  # VSCode settings (optional)
├── config/
│   └── config.yaml           # Main configuration file (DB connections, collections, auth)
├── data/                     # Default data storage (e.g., for Docker volumes)
│   └── docker/
│       └── chroma/
│           └── db/
├── deployment/
│   └── docker-compose-chroma.yml # Docker Compose specifically for the ChromaDB service
├── rag/                      # Main application source code
│   ├── api/                  # API routes, models, application setup
│   │   ├── routes/           # Specific route modules (auth, items, search, rag_info, etc.)
│   │   ├── __init__.py
│   │   ├── app.py            # FastAPI app creation & startup logic
│   │   └── models.py         # Pydantic API data models
│   ├── db/                   # Database interaction logic
│   │   ├── __init__.py
│   │   ├── postgres_reader.py # Reads classification data from PostgreSQL
│   │   └── vector_store.py   # ChromaDB vector store interaction (CRUD, search)
│   ├── utils/                # Utility functions (if any)
│   ├── __init__.py
│   ├── config.py             # Configuration loading logic (reads config.yaml/env vars)
│   └── main.py               # Simple script to run uvicorn (alternative entry point)
├── .env                      # Environment variables (optional, for local overrides)
├── .gitignore
├── requirements.txt          # Python dependencies for the project
├── start-rag-docker.bat      # Windows script to start ChromaDB using Docker Compose
├── start-rag-local.bat       # Windows script to start the API locally using Conda (databases must be running)
└── README.md                 # This file
```

## Features

- **Vector Store:** Uses ChromaDB for efficient storage and semantic search of text data.
- **Relational Data:** Integrates with PostgreSQL to fetch structured classification data (e.g., UNSPSC categories).
- **Configurable Collections:** Supports multiple, named ChromaDB collections defined in `config.yaml` (e.g., `unspsc_collection`, `common_collection`, `manual_info_collection`).
- **Manual RAG Info Management:** Provides CRUD API endpoints (`/v1/rag-info`) to manage key-value textual information for RAG.
- **Semantic Search:** Offers similarity search within specific collections or across multiple collections.
- **Optional Authentication**: Built-in OAuth2 authentication (Bearer tokens) that can be enabled/disabled via configuration.
- **Startup Data Population:** Automatically checks and populates the configured UNSPSC collection in ChromaDB from PostgreSQL on API startup if the collection is empty.
- **Easy Configuration**: Central `config/config.yaml` file with environment variable overrides for flexibility.
- **Docker Support**: Includes Docker Compose configuration (`deployment/docker-compose-chroma.yml`) for easily running the ChromaDB service.
- **Local Development Scripts:** Provides `.bat` scripts for starting ChromaDB via Docker (`start-rag-docker.bat`) and running the API locally via Conda (`start-rag-local.bat`).

## Local Setup (Conda - Recommended)

### Prerequisites

- [Conda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html) (Anaconda or Miniconda)
- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Optional, needed if using `start-rag-docker.bat` for ChromaDB)
- A running PostgreSQL instance (Version 12+ recommended)

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd unspsc-classifier
```

### 2. Create and Activate Conda Environment

This project requires Python 3.10. Using other versions (especially newer ones like 3.12+) may cause dependency conflicts.

```bash
# Create a new conda environment with Python 3.10
conda create -n classification-rag python=3.10

# Activate the environment
conda activate classification-rag
```

### 3. Install Requirements

It's recommended to run pip via `python -m pip` to ensure you're using the interpreter and pip from the active Conda environment, especially if you have multiple Python installations.

```bash
# Ensure pip, setuptools, and wheel are up-to-date within the environment
python -m pip install --upgrade pip setuptools wheel

# Install project dependencies from the root requirements.txt file
python -m pip install -r requirements.txt
```

### 4. Setup Databases

You need both PostgreSQL and ChromaDB running and accessible by the API.

**PostgreSQL:**
- Ensure your PostgreSQL server is running.
- Create the database and user specified in your `config/config.yaml` (or use the defaults). You might need to run initialization scripts to create the necessary tables (classification_systems, categories, etc.) if they don't exist.

**ChromaDB:** You have two main options:

**Option A (Docker - Recommended for Chroma):** Use the provided script to run ChromaDB in a Docker container. This handles persistence automatically.
```bash
# Run from the project root directory
start-rag-docker.bat
```

This will start ChromaDB and make it available (by default) at http://localhost:8000. Data will be persisted in `data/docker/chroma/db`.

**Option B (Manual):** If you prefer not to use Docker, you need to install and run the ChromaDB server manually following their documentation. Ensure it's running on the host and port configured in `config/config.yaml`.

### 5. Configure the Application

Edit `config/config.yaml`. Pay close attention to:
- `postgres`: host, port, user, password, dbname
- `chromadb`: host, port, collection names (unspsc_collection, common_collection, manual_info_collection, etc.)
- `server`: host, port for the API itself
- `auth`: enabled (true/false), secret_key (change this!), admin credentials.

Alternatively, set environment variables to override config.yaml settings (e.g., `set PG_HOST=192.168.1.100`, `set CHROMA_PORT=8001`). Environment variables take precedence.

### 6. Run the API

Make sure your `classification-rag` Conda environment is active and you are in the project's root directory (unspsc-classifier).

```bash
# Start the FastAPI application using uvicorn
# --reload automatically restarts the server when code changes (for development)
python -m uvicorn rag.api.app:app --host 0.0.0.0 --port 8090 --reload
```

The API server will start, and on the first run (if the UNSPSC collection is empty), it will attempt to connect to PostgreSQL and populate the ChromaDB collection. Watch the console output for logs.

### 7. Access the API

- API Status: http://localhost:8090/
- Health Check: http://localhost:8090/health
- Swagger UI (Interactive Docs): http://localhost:8090/docs
- ReDoc (Alternative Docs): http://localhost:8090/redoc

### Using the start-rag-local.bat Script (Shortcut)

Once you have completed steps 1-3 (Clone, Create Conda Env, Install Requirements) and ensured your databases (PostgreSQL and ChromaDB) are running and configured correctly in `config/config.yaml`, you can use the `start-rag-local.bat` script as a shortcut to run the API:

1. Edit `start-rag-local.bat` to ensure `CONDA_ENV_PATH` points to your correct `classification-rag` environment location.
2. Double-click `start-rag-local.bat` or run it from the command line in the project root.
   
This script activates the Conda environment and runs the uvicorn command for you.

### Data Persistence with start-rag-local.bat

By default, when running the RAG service with `start-rag-local.bat`, it uses an in-memory ChromaDB client which does not persist data between restarts. To enable data persistence, use the `-p` or `--persistent` flag:

```bash
# Run with persistence enabled
.\start-rag-local.bat -p
```

or 

```bash
# Alternative long form
.\start-rag-local.bat --persistent
```

**What the Persistence Flag Does:**

- Starts a ChromaDB server in a separate window with persistent storage
- Stores data in the `data\docker\chroma` directory (same location used by Docker)
- Keeps the ChromaDB server running even after you close the RAG service
- Ensures your embeddings and vector data are preserved between restarts

**Benefits of Using Persistence Mode:**

- No need to reload data into ChromaDB each time you restart the service
- Faster startup times after the initial data load
- Consistent search results between service restarts
- Same data persistence location as the Docker setup for compatibility

**Note:** The ChromaDB server window remains open when you stop the RAG service. This allows you to restart the RAG service without losing data. You can manually close the ChromaDB server window when you're done working with the RAG service.

## API Usage Examples

(Refer to the Swagger UI at `/docs` for detailed request/response models and to try out endpoints interactively.)

### Status Endpoints

- `GET /`: Get API status, ChromaDB connection status, list of collections, and auth status.
- `GET /health`: Simple health check, returns `{"status": "ok"}`.

### Authentication (if enabled in config)

**Get Token:**
```
POST /token
Content-Type: application/x-www-form-urlencoded
Body: username=your_admin_user&password=your_admin_password
```

(Default credentials are often admin/admin but should be changed in config.yaml)

**Use Token:** Include the received token in the Authorization header for protected endpoints:
```
Authorization: Bearer <your_access_token>
```

### Collections

- `GET /collections`: List all available ChromaDB collections and their item counts.
- `POST /collection/{collection_name}`: Create a new, empty collection (requires auth if enabled).
- `DELETE /collection/{collection_name}`: Delete a collection (requires auth if enabled).

### Adding Data (Example: UNSPSC Categories)

This endpoint is typically used by backend processes or data loading scripts. The API startup logic already handles initial UNSPSC population from PostgreSQL.

```
POST /add_batch
Content-Type: application/json
Body: {
  "items": [
    {
      "code": "43211503",
      "name": "Notebook computer",
      "description": "A portable personal computer primarily designed for mobile use.",
      "hierarchy": "Information Technology Broadcasting and Telecommunications > Technology Broadcasting and Telecommunications Machinery and Accessories > Computer Equipment and Accessories > Computer > Notebook computer",
      "metadata": {"version": "21"}
    }
    // ... more items
  ],
  "collection_name": "unspsc_categories" // Or your configured UNSPSC collection name
}
```

### Searching

**Search in a specific collection:**
```
GET /search?query=portable%20computer&collection_name=unspsc_categories&limit=5
```

**Search across all (non-manual) collections:**
```
GET /search_all?query=computer%20accessory&limit_per_collection=3&min_score=0.5
```

### Manual RAG Info Management (`/v1/rag-info`)

These endpoints manage key-value text snippets stored in the `manual_info_collection`. Authentication is required if enabled.

**Create Item:**
```
POST /v1/rag-info
Content-Type: application/json
Body: { "key": "company_policy_returns", "description": "Our return policy allows returns within 30 days with proof of purchase." }
```

**List Items (Paginated):**
```
GET /v1/rag-info?page=1&limit=10&search=policy
```

**Get Specific Item:**
```
GET /v1/rag-info/company_policy_returns
```

**Update Item:**
```
PUT /v1/rag-info/company_policy_returns
Content-Type: application/json
Body: { "description": "Our updated return policy allows returns within 60 days with proof of purchase for store credit." }
```

**Delete Item:**
```
DELETE /v1/rag-info/company_policy_returns
```

## Troubleshooting

### ChromaDB Connection Issues:

- If using Docker (`start-rag-docker.bat`), ensure the container is running: `docker ps --filter name=chromadb`. Check Docker Desktop.
- If running manually, ensure the Chroma server process is active.
- Verify the host and port in `config/config.yaml` under `chromadb:` match where ChromaDB is actually listening.
- Check network connectivity/firewalls between the API server and ChromaDB.
- Test basic Chroma connectivity: `curl http://<chroma_host>:<chroma_port>/api/v1/heartbeat` (replace host/port).

### PostgreSQL Connection Issues:

- Ensure the PostgreSQL server is running and accessible from where the API is running.
- Verify host, port, user, password, and dbname in `config/config.yaml` under `postgres:`.
- Check PostgreSQL logs for connection errors.
- Ensure the specified database and user exist and the user has permissions.

### Dependency Errors during pip install:

- Make sure you are using Python 3.10 within your activated `classification-rag` Conda environment. Check with `python --version`.
- Run `python -m pip install -r requirements.txt` instead of just `pip install ...`.

### API Errors (500 Internal Server Error):

- Check the API's console output for detailed error messages and tracebacks.
- Look for logs in `rag_service.log` (if logging is configured to a file, which it seems to be in `rag/main.py`).

### Authentication Issues:

- Ensure `auth.enabled` is set correctly in `config/config.yaml`.
- Double-check username/password when requesting a token via `POST /token`.
- Ensure the `Authorization: Bearer <token>` header is correctly sent for protected routes.
- Verify the `SECRET_KEY` in config.yaml is consistent if running multiple instances.

## Docker Deployment Notes

The provided `deployment/docker-compose-chroma.yml` and `start-rag-docker.bat` script are primarily for running the ChromaDB service in Docker easily during local development.

Deploying the entire application (API + ChromaDB + PostgreSQL) to production using Docker would require a more comprehensive docker-compose.yml file that defines services for the API (using a Dockerfile to build the API image), PostgreSQL, and ChromaDB, linking them together with appropriate networking and volume mounts.

## Testing with Postman

A Postman collection might be available (check project files or ask maintainer). If using one:

1. Import the collection into Postman.
2. Set the base URL variable (e.g., `baseUrl`) to `http://localhost:8090`.
3. If auth is enabled, run the "Get Token" request first and configure Postman to use the Bearer token automatically or copy-paste it into the Authorization header for other requests.
4. Explore and test the available endpoints, including the `/v1/rag-info` routes.
