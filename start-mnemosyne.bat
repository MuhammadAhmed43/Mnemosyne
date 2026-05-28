@echo off
REM One-click start for the Mnemosyne engine (loopback HTTP on :7432).
REM Ollama runs on its own as a background app after install, so we just
REM start the engine. Leave this window open while you work.
cd /d C:\CotrexAI
REM Force the stronger extraction model regardless of an older saved config.json
REM (which may still pin phi4-mini). To trade quality for speed, change this to
REM qwen2.5:3b-instruct. The engine falls back gracefully if it isn't installed.
set MNEMOSYNE_OLLAMA_MODEL=qwen2.5:7b-instruct
echo Starting Mnemosyne engine on http://localhost:7432  (model: %MNEMOSYNE_OLLAMA_MODEL%, Ctrl+C to stop)
python -m backend.main
pause
