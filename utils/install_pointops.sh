#!/bin/bash

# Installing Pointops
echo "Installing Pointops..."
cd /app/pointops && python setup.py install --user && cd /app

echo "Pointops has been installed correctly."