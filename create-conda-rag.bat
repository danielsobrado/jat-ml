@echo off
echo ====================================================
echo Creating conda environment for RAG service
echo ====================================================

REM Check if conda is available
where conda >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Conda is not available in PATH.
    echo Please install Anaconda or Miniconda and try again.
    exit /b 1
)

REM Check if environment exists and remove if it does
echo Checking for existing environment 'classification-rag'...
conda env list | findstr "classification-rag" >nul
if %errorlevel% equ 0 (
    echo Found existing environment. Removing...
    call conda remove -y --name classification-rag --all
)

REM Create the conda environment
echo Creating new conda environment 'classification-rag'...
call conda create -y --name classification-rag python=3.10

REM Activate the environment and install requirements
echo Activating environment and installing dependencies...
call conda activate classification-rag

REM Install pip packages from requirements.txt
echo Installing packages from rag/requirements.txt...
pip install -r rag/requirements.txt

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
echo     conda activate classification-rag
echo.
echo To start the RAG service locally, run:
echo     .\start-rag-local.bat
echo ====================================================

exit /b 0