#!/bin/bash

# Falla el script si hay un error
set -e

# Activar el entorno Conda
echo "Activando el entorno Conda: myenv"
conda run -n myenv <<EOF

# Instalar paquetes de Python
echo "Instalando bibliotecas de Python..."
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

# Instalar bibliotecas del sistema
echo "Instalando bibliotecas del sistema..."
apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libgl1-mesa-dev \
    libglib2.0-0

# Instalar PyTorch Geometric y dependencias
echo "Instalando PyTorch Geometric y sus dependencias..."
pip install torch-geometric==2.4.0
pip install torch-scatter==2.0.9 torch-sparse==0.6.12 torch-spline-conv==1.2.1 torch-cluster==1.5.9 -f https://data.pyg.org/whl/torch-1.10.0+cu111.html

# Instalar Pointops
# cd pointops ; python3 setup.py install ; cd ..

EOF

echo "Todas las dependencias han sido instaladas correctamente."


