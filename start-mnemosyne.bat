@echo off
REM One-click start for the Mnemosyne engine (loopback HTTP on :7432).
REM Ollama runs on its own as a background app after install, so we just
REM start the engine. Leave this window open while you work.
cd /d C:\CotrexAI
echo Starting Mnemosyne engine on http://localhost:7432  (Ctrl+C to stop)
python -m backend.main
pause
