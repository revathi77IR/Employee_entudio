#!/bin/bash

# Make sure the script stops on first error
set -e

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Verify installations
echo "Checking installations..."
pip list | grep opencv
pip list | grep dlib
pip list | grep face-recognition

echo "Setup completed successfully!"
