@echo off
rem Bot V: one click starts the model server, Bot V, OpenJarvis and the browser.
rem The first run creates the Python environment and installs everything.
rem The whole script is one block so cmd reads it fully before running it:
rem an update from GitHub may replace this file while it runs.
(
    setlocal
    cd /d "%~dp0"
    title Bot V

    if not exist ".venv\Scripts\python.exe" (
        echo [..] First run: creating the Python 3.13 environment...
        py -3.13 -m venv .venv
        if errorlevel 1 (
            echo [!!] Python 3.13 was not found. Install it with:  py install 3.13
            pause
            exit /b 1
        )
        ".venv\Scripts\python.exe" -m pip install --upgrade pip
        ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt -r requirements-openjarvis.txt
        if errorlevel 1 (
            echo [!!] Installing the packages failed. See the messages above.
            pause
            exit /b 1
        )
    )

    ".venv\Scripts\python.exe" -m bot_v.launch %*
    echo.
    echo Bot V stopped. Press any key to close this window.
    pause >nul
    exit /b
)
