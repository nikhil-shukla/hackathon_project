#!/bin/bash
set -e

echo "🚀 Installing pytest-cov..."
pip install pytest-cov -q

echo "📊 Running tests with coverage analysis..."
python -m pytest --cov=main --cov-report=term-missing test_main.py
