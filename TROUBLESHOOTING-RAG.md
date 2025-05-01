# RAG Service Troubleshooting Guide

## Configuration Issues

### RAG Service Not Starting

**Issue**: Classification service fails to start with "RAG is enabled but service is not available"

**Solution**:
1. Check RAG configuration in `config/config.yaml`:
   ```yaml
   database:
     ragServiceUrl: "http://localhost:8000"
     ragEnabled: false  # Set to true only if you need RAG functionality
   ```

2. If RAG is enabled:
   - Start the RAG service: `start-rag.bat`
   - Wait for the service to be fully available
   - Check service status at http://localhost:8000/api/v1/heartbeat

3. If you don't need RAG:
   - Set `ragEnabled: false` in config.yaml
   - Restart the classification service

### Connection Issues

**Issue**: RAG service is running but classification service can't connect

**Debug Steps**:
1. Verify ChromaDB container status:
   ```powershell
   docker ps | Select-String chromadbapi
   ```

2. Check ChromaDB logs:
   ```powershell
   docker logs chromadbapi
   ```

3. Verify connection settings in `config-chroma.yaml`:
   ```yaml
   chroma:
     host: chromadbapi  # Use service name in docker-compose
     port: 8000
   ```

## RAG Service Management

### Starting the Service

1. Using the startup script:
   ```bash
   start-rag.bat
   ```
   This will:
   - Start ChromaDB in a Docker container
   - Persist data in `data/docker/chroma/db`
   - Make RAG available at http://localhost:8000

2. Manual container management:
   ```bash
   # Start existing container
   docker start chromadb

   # Check status
   docker ps | findstr chromadb
   ```

### Data Persistence

RAG data is stored in:
- `data/docker/chroma/db` relative to project root
- Survives container restarts
- Back up this directory before updates

### Environment Setup

Required environment variables:
```bash
# Windows
set CHROMA_HOST=localhost
set CHROMA_PORT=8000
set PYTHONPATH=C:\path\to\unspsc-classifier

# Linux/Mac
export CHROMA_HOST=localhost
export CHROMA_PORT=8000
export PYTHONPATH=/path/to/unspsc-classifier
```

## Common Errors

### Python Module Issues

**Error**: `No module named rag.main`

**Solution**:
1. Check module structure:
   ```
   rag/
   ├── api/
   ├── db/
   ├── utils/
   └── __init__.py
   ```

2. Verify PYTHONPATH includes project root

### NumPy Compatibility

**Error**: `AttributeError: np.float_ was removed in the NumPy 2.0 release`

**Solution**:
1. Pin numpy version:
   ```
   numpy==1.24.3  # Required for chromadb compatibility
   ```

2. Pin chromadb version:
   ```
   chromadb==0.4.18  # Known working version
   ```

## Testing

### API Testing

1. Use the included test script:
   ```bash
   test-rag-apis.bat
   ```

2. Manual endpoint testing:
   ```bash
   # Health check
   curl http://localhost:8000/api/v1/heartbeat

   # Search test
   curl "http://localhost:8000/search?collection_name=UNSPSC&query=test&limit=3"
   ```

### Common Test Issues

1. **Connection refused**: RAG service not running
   - Check Docker container status
   - Verify port 8000 is available
   - Check for firewall issues

2. **Collection not found**: Missing or incorrect data
   - Verify collection exists
   - Check collection name case sensitivity
   - Ensure data was properly imported

3. **Search returns no results**: Data or query issues
   - Verify collection has data
   - Check query formatting
   - Review similarity thresholds