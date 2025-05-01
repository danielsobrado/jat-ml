@echo off
setlocal EnableDelayedExpansion

:: Set base URL
set API_URL=http://localhost:8090

:: Function to wait for service to be ready
echo Waiting for RAG service to be ready...
:check_service
curl -s -X GET "%API_URL%/health" > nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 2 /nobreak > nul
    goto :check_service
)
echo Service is ready!

:: Test endpoints
echo.
echo Testing API endpoints...
echo.

:: Test health endpoint
echo Testing health endpoint...
curl -s -X GET "%API_URL%/health"
echo.
echo.

:: Test collections endpoint
echo Testing collections endpoint...
curl -s -X GET "%API_URL%/collections"
echo.
echo.

:: Create a test collection
echo Creating test collection...
curl -s -X POST "%API_URL%/collection/test_collection"
echo.
echo.

:: Test adding sample data (using a file to avoid escaping issues)
echo Adding sample data...
echo {"items":[{"code":"43211503","name":"Notebook computer","description":"A portable personal computer","hierarchy":"IT > Hardware > Computers"}],"collection_name":"test_collection"} > temp_payload.json
curl -s -X POST "%API_URL%/add_batch" -H "Content-Type: application/json" -d @temp_payload.json
del temp_payload.json
echo.
echo.

:: Test search
echo Testing search...
curl -s -X GET "%API_URL%/search?query=computer&collection_name=test_collection&limit=5"
echo.
echo.

:: Clean up test collection
echo Cleaning up test collection...
curl -s -X DELETE "%API_URL%/collection/test_collection"
echo.
echo.

echo All tests completed!
endlocal