#!/bin/bash

# Simple HTTP Server Launcher for Store Viewer
# This serves the index.html and combined.json files

echo "=========================================="
echo "Store Locator Viewer"
echo "=========================================="
echo ""
echo "Starting HTTP server on port 8000..."
echo "Opening browser at: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Open browser after a short delay
(sleep 2 && open http://localhost:8000) &

# Start viewer server (static files + /api/analyze-brand endpoint)
python3 serve.py
