@echo off
setlocal EnableDelayedExpansion

REM --- Configuration ---
REM Set the NAME of your Conda environment
set CONDA_ENV_NAME=classification-rag
REM Set the path to your configuration file relative to this script's location
set CONFIG_FILE_RELATIVE=config\config.yaml
REM Set the host and port for the Uvicorn server (should match config.py defaults or config.yaml)
set SERVER_HOST=0.0.0.0
set SERVER_PORT=8090
REM ChromaDB server settings
set CHROMA_HOST=localhost
set CHROMA_PORT=8000
set CHROMA_DATA_DIR=data\docker\chroma
REM Authentication settings
set AUTH_ENABLED=false
REM Default to persistence mode
set PERSISTENT=true
REM --- End Configuration ---

REM Process command-line parameters
set CHROMA_PID=

:parse_args
if "%1"=="" goto end_parse_args
if /i "%1"=="--no-persist" set PERSISTENT=false
if /i "%1"=="-n" set PERSISTENT=false
if /i "%1"=="--auth" set AUTH_ENABLED=true
shift
goto parse_args
:end_parse_args

echo Starting RAG service locally using 'conda run'...
echo ==================================

REM 1. Navigate to the Project Root Directory and capture it
cd /d "%~dp0"
set PROJECT_ROOT=%cd%
echo Changed directory to project root: %PROJECT_ROOT%

REM 2. Set Environment Variables needed by the Python script
REM *** Add the Project Root to PYTHONPATH ***
set PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%
echo Setting PYTHONPATH=%PYTHONPATH%

REM Set config path
set CONFIG_PATH=%CONFIG_FILE_RELATIVE%
echo Setting CONFIG_PATH=%CONFIG_PATH%

REM Start ChromaDB server if persistence is enabled (default)
if "%PERSISTENT%"=="true" (
    echo Persistence mode enabled default. Starting ChromaDB server
    
    REM Check if ChromaDB port is already in use
    netstat -ano | findstr ":%CHROMA_PORT% " | findstr "LISTENING" > temp_chroma.txt
    set "size=0"
    for %%A in (temp_chroma.txt) do set size=%%~zA
    if defined size (
        if !size! GTR 0 (
            echo ChromaDB port %CHROMA_PORT% is already in use.
            echo Another ChromaDB server might be running. Will try to connect to it.
        ) else (
            REM Create the data directory if it doesn't exist
            if not exist "%CHROMA_DATA_DIR%" (
                echo Creating ChromaDB data directory: %CHROMA_DATA_DIR%
                mkdir "%CHROMA_DATA_DIR%" 2>nul
            )
            
            REM Start ChromaDB server in a separate window
            echo Starting ChromaDB server with persistent storage at %CHROMA_DATA_DIR%...
            start "ChromaDB Server" cmd /K "call conda activate %CONDA_ENV_NAME% && chroma run --path %PROJECT_ROOT%\%CHROMA_DATA_DIR% --host %CHROMA_HOST% --port %CHROMA_PORT% || echo ChromaDB server failed to start! && pause"
            
            REM Wait for ChromaDB server to start
            echo Waiting for ChromaDB server to start...
            timeout /t 5 /nobreak > nul
            
            REM Set environment variables for the RAG service to connect to ChromaDB
            set CHROMA_HOST=%CHROMA_HOST%
            set CHROMA_PORT=%CHROMA_PORT%
        )
    ) else (
        REM temp_chroma.txt does not exist or size not set
        REM Assume port is not in use
        if not exist "%CHROMA_DATA_DIR%" (
            echo Creating ChromaDB data directory: %CHROMA_DATA_DIR%
            mkdir "%CHROMA_DATA_DIR%" 2>nul
        )
        echo Starting ChromaDB server with persistent storage at %CHROMA_DATA_DIR%...
        start "ChromaDB Server" cmd /K "call conda activate %CONDA_ENV_NAME% && chroma run --path %PROJECT_ROOT%\%CHROMA_DATA_DIR% --host %CHROMA_HOST% --port %CHROMA_PORT% || echo ChromaDB server failed to start! && pause"
        echo Waiting for ChromaDB server to start...
        timeout /t 5 /nobreak > nul
        set CHROMA_HOST=%CHROMA_HOST%
        set CHROMA_PORT=%CHROMA_PORT%
    )
    del temp_chroma.txt 2>nul

    REM Wait until ChromaDB server port is listening
    echo Waiting for ChromaDB server to become available on port %CHROMA_PORT%...
    :wait_chroma
    netstat -ano | findstr ":%CHROMA_PORT% " | findstr "LISTENING" > temp_chroma2.txt
    set "size2=0"
    for %%A in (temp_chroma2.txt) do set size2=%%~zA
    if not defined size2 (
        timeout /t 1 /nobreak >nul
        goto wait_chroma
    ) else (
        if !size2! GTR 0 (
            echo ChromaDB server is up and listening on port %CHROMA_PORT%.
            del temp_chroma2.txt 2>nul
        ) else (
            timeout /t 1 /nobreak >nul
            goto wait_chroma
        )
    )
) else (
    echo Persistence mode disabled via command line flag. Using in-memory storage.
)

REM Clean up any existing temp file
del temp_ports.txt 2>nul

REM Check if port is already in use with a focused command
echo Checking if port %SERVER_PORT% is available...
netstat -ano | findstr ":%SERVER_PORT% " | findstr "LISTENING" > temp_ports.txt

REM Get file size to see if any processes were found
set "size=0"
for %%A in (temp_ports.txt) do set size=%%~zA
if defined size (
    if %size% GTR 0 (
        REM Get the PID from the netstat output - use a simpler and more robust method
        for /f "tokens=2,5" %%a in ('type temp_ports.txt ^| findstr /r /c:"LISTENING"') do (
            REM Extract the PID from the last column
            set "pid=%%b"
            echo Found process with PID: !pid! using port %SERVER_PORT%
        )
        
        REM Only proceed if we have a valid PID
        if defined pid (
            if !pid! NEQ "" (
                REM Get the process name
                echo Identifying process name...
                for /f "tokens=1" %%p in ('tasklist /fi "PID eq !pid!" ^| findstr "!pid!"') do (
                    set "proc_name=%%p"
                )
                
                if defined proc_name (
                    if "!proc_name!" NEQ "" (
                        echo The port is being used by: !proc_name! (PID: !pid!)
                    ) else (
                        echo Unable to determine process name, but found PID: !pid!
                    )
                    
                    choice /C YNR /M "Do you want to [Y]es terminate this process, [N]o abort startup, or [R]etry with the port?"
                    if !errorlevel!==1 (
                        echo Attempting to terminate process !pid!...
                        taskkill /F /PID !pid!
                        if !errorlevel! neq 0 (
                            echo ERROR: Failed to terminate process. Please free up port %SERVER_PORT% manually.
                            del temp_ports.txt 2>nul
                            pause
                            exit /b 1
                        )
                        echo Process terminated successfully.
                        timeout /t 2 /nobreak >nul
                    ) else if !errorlevel!==2 (
                        echo Aborting startup. You may need to:
                        echo 1. Ensure any previous RAG service instances are stopped
                        echo 2. Check for other applications using port %SERVER_PORT%
                        echo 3. Try running 'netstat -ano | findstr :%SERVER_PORT%' to identify the process
                        del temp_ports.txt 2>nul
                        pause
                        exit /b 1
                    ) else (
                        echo Retrying connection...
                        timeout /t 2 /nobreak >nul
                    )
                ) else (
                    echo No valid process found using port %SERVER_PORT%. Continuing with startup...
                )
            ) else (
                echo No valid PID found. Continuing with startup...
            )
        ) else (
            echo No valid PID found. Continuing with startup...
        )
    ) else (
        echo Port %SERVER_PORT% is available. Continuing with startup...
    )
) else (
    echo Port %SERVER_PORT% is available. Continuing with startup...
)

REM Clean up temp file
del temp_ports.txt 2>nul

REM Run the main.py directly rather than using uvicorn
echo Starting RAG service on %SERVER_HOST%:%SERVER_PORT%...
if "%PERSISTENT%"=="true" (
    echo [Persistence Mode] RAG service will connect to ChromaDB at %CHROMA_HOST%:%CHROMA_PORT%
)
if "%AUTH_ENABLED%"=="true" (
    echo [Authentication Enabled] Authentication is enabled for the RAG service.
    set ENABLE_AUTH=true
) else (
    echo [Authentication Disabled] Authentication is disabled for the RAG service.
    set ENABLE_AUTH=false
)
conda run -n %CONDA_ENV_NAME% --no-capture-output --live-stream --cwd "%PROJECT_ROOT%" ^
    python -m rag.main ^
    --server-port=%SERVER_PORT% ^
    --server-host=%SERVER_HOST%

echo ==================================
echo RAG service stopped.

REM If we started a ChromaDB server, we should note that it's still running
if "%PERSISTENT%"=="true" (
    echo NOTE: The ChromaDB server is still running in a separate window.
    echo You can close it manually when you're done or leave it running for future sessions.
)

pause
endlocal
goto :eof

:eof
echo Script finished.