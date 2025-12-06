#!/bin/bash

# Zuper-NetSuite Dashboard Startup Script

echo "=========================================="
echo "Zuper-NetSuite Monitoring Dashboard"
echo "=========================================="
echo ""

# Check if database exists
if [ ! -f "zuper_netsuite.db" ]; then
    echo "⚠️  Database not found. Running initial sync..."
    python3 sync_to_database.py
    echo ""
fi

# Start the dashboard
echo "Starting dashboard..."
echo "Dashboard will be available at: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the dashboard"
echo "=========================================="
echo ""

python3 dashboard.py
