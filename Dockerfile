FROM pytorch/pytorch:1.10.0-cuda11.3-cudnn8-devel

WORKDIR /app

RUN apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu1804/x86_64/3bf863cc.pub

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    wget \
    curl \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

SHELL ["bash", "-c"]

RUN conda create -n myenv python=3.8.0 -y && conda clean --all -y

RUN echo "conda activate myenv" >> ~/.bashrc
ENV CONDA_DEFAULT_ENV=myenv
ENV PATH="/opt/conda/envs/myenv/bin:$PATH"

COPY . /app

RUN conda run -n myenv pip install torch==1.10.1+cu113 torchvision==0.11.2+cu113 torchaudio==0.10.1+cu113 --extra-index-url https://download.pytorch.org/whl/cu113 && conda clean --all -y

# Comando por defecto
CMD ["sleep", "infinity"]

# Instala las dependencias del archivo new_requirements.txt dentro del entorno Conda
# RUN conda run -n myenv pip install --no-cache-dir -r /app/new_requirements.txt && \
#     pip install torch==1.10.1+cu113 torchvision==0.11.2+cu113 torchaudio==0.10.1+cu113 --extra-index-url https://download.pytorch.org/whl/cu113 && \
#     conda clean --all --yes && \
#     pip cache purge