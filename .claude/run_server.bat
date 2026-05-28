@echo off
set NAEGIWANGBANK_SESSION_SECRET=dev-secret-for-testing-only
python -m uvicorn server.main:app --host 127.0.0.1 --port 8765 --log-level warning
