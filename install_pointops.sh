#!/bin/bash

# Installing Pointops
echo "Installing Pointops..."
cd /app/pointops && python setup.py install --user && cd /app

# Clean up
echo "Cleaning files..."
rm -rf /app/pointops
rm -rf /app/install_pointops.sh

echo "Pointops has been installed correctly."