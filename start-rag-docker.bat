@echo off
setlocal

:: Set paths
set DEPLOYMENT_PATH=%~dp0rag\deployment
set COMPOSE_FILE=docker-compose-chroma.yml
set DOCKER_CHROMA_PATH=%~dp0data\docker\chroma\db

:: Create data directory if it doesn't exist
if not exist "%DOCKER_CHROMA_PATH%" (
    echo Creating ChromaDB data directory...
    mkdir "%DOCKER_CHROMA_PATH%"
)

:: Change to deployment directory
cd %DEPLOYMENT_PATH%

echo Starting RAG services...
echo Note: Press Ctrl+C to stop the services

:: Start services in attached mode to see logs
docker compose -f %COMPOSE_FILE% up

:: The script will wait here while services are running

echo Services stopped.
echo You can restart them by running this script again.

endlocal