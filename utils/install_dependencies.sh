#!/bin/bash

# Active Conda
echo "Activating Conda environment"
source /opt/conda/etc/profile.d/conda.sh
conda activate myenv

# Installing PyTorch
echo "Installing PyTorch..."
pip install torch==1.10.1+cu113 torchvision==0.11.2+cu113 torchaudio==0.10.1+cu113 --extra-index-url https://download.pytorch.org/whl/cu113
pip install torch-geometric==2.4.0
pip install torch-scatter==2.0.9 torch-sparse==0.6.12 torch-spline-conv==1.2.1 torch-cluster==1.5.9 -f https://data.pyg.org/whl/torch-1.10.0+cu111.html

# Installing Python libraries
echo "Installing Python libraries..."
pip install smplx
pip install open3d
pip install opencv-python
pip install einops
pip install timm
pip install botocore
pip install easydict
pip install chumpy==0.70
pip install fvcore
pip install thop
pip install numpy==1.23.0

# Clean up
echo "Cleaning file..."
rm -rf /app/install_dependencies.sh

echo "All the dependencies have been installed correctly."
