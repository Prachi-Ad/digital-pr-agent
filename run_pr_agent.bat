@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: The Python virtual environment was not found.
    echo Expected folder: .venv\Scripts\activate.bat
    echo Make sure this file is inside your project folder.
    pause
    exit /b 1
)

if not defined OPENAI_API_KEY (
    echo ERROR: OPENAI_API_KEY is not set for this Windows session.
    echo Set OPENAI_API_KEY in your Windows user environment variables,
    echo then close and reopen this launcher.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
streamlit run app.py
pause
