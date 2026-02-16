#!/bin/bash
# Azure App Service startup script for FastAPI
gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 120
