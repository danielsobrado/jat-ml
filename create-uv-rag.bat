@echo off
echo ====================================================
echo Creating uv environment for RAG service
echo ====================================================

REM Check if python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not available in PATH.
    echo Please install Python and try again.
    exit /b 1
)

REM Define the environment directory
set "ENV_DIR=%~dp0.venv"

REM Check if environment exists and remove if it does
echo Checking for existing environment...
if exist "%ENV_DIR%" (
    echo Found existing environment. Removing...
    rmdir /s /q "%ENV_DIR%"
)

echo Installing uv if it's not already installed...
pip install -U uv

REM Create the virtual environment
echo Creating new uv virtual environment...
uv venv "%ENV_DIR%" --python=3.11

REM Activate the virtual environment and install requirements
echo Activating environment and installing dependencies...
call "%ENV_DIR%\Scripts\activate"

REM Install all requirements using uv
echo Installing packages using uv...
uv pip install -r requirements.txt

REM Check installation status
if %errorlevel% neq 0 (
    echo Error: Failed to install some dependencies.
    echo Please check the error messages above.
    exit /b 1
)

echo ====================================================
echo Environment setup complete!
echo ====================================================
echo.
echo To activate the environment, run:
echo     call "%~dp0.venv\Scripts\activate"
echo.
echo To start the RAG service locally, run:
echo     .\start-rag-local.bat
echo ====================================================

exit /b 0