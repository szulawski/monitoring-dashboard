#!/bin/bash

set -e

echo "--- Cleaning up project environment ---"
echo "Removing old virtual environment (.venv)..."
rm -rf .venv

echo "Removing Python cache files (__pycache__)..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

echo "Removing pytest cache (.pytest_cache)..."
rm -rf .pytest_cache

echo -e "\n--- Rebuilding project environment ---"

echo "Creating new virtual environment in ./.venv/..."
python3 -m venv .venv

echo "Upgrading pip and installing dependencies from requirements.txt..."
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo -e "\n--- Setup complete! ---"
echo "To work in the new environment after this script finishes, run:"
echo "source .venv/bin/activate"
echo -e "\n--- Running tests now... ---"

# ./.venv/bin/pytest