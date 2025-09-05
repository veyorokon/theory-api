ARG BASE_IMAGE=python
ARG BASE_TAG=3.6
ARG PORT
FROM ${BASE_IMAGE}:${BASE_TAG}

ENV \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

RUN apt-get update -y
RUN apt-get install -y git cmake g++ pkg-config curl tar file xz-utils build-essential wget libpng-dev libtiff-dev libjpeg-dev libsm6 libxext6 libfontconfig1 libxrender1 locales ca-certificates python3-dev libpq-dev postgresql-client && rm -rf /var/lib/apt/lists/*

RUN mkdir /app

#Install miniconda
RUN \
    locale-gen en_US.UTF-8 && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"; \
    elif [ "$ARCH" = "aarch64" ]; then \
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh"; \
    else \
    echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    wget -q -P /tmp --no-check-certificate $MINICONDA_URL && \
    PREFIX=/usr/local/anaconda && \
    bash /tmp/Miniconda3-latest-Linux-*.sh -bfp $PREFIX && \
    rm -rf /tmp/Miniconda3-latest-Linux-*.sh && \
    export PATH=$PREFIX/bin:$PATH && \
    printf "channels:\n  - conda-forge\n  - nodefaults\n" > $PREFIX/.condarc && \
    PYVER=$(python -c 'import sys; a,b=sys.version_info[:2]; print("{:d}.{:d}".format(a,b))') && \
    echo "######### $PYVER ##########"

ENV PATH=/usr/local/anaconda/bin:$PATH

# Install pip from conda-forge
RUN conda install -y -c conda-forge --override-channels pip

# install dependencies

RUN env
COPY ./code /app
COPY ./conda /app/conda

COPY ./code/entrypoint.sh /entrypoint.sh

# Skip conda env update if environment.yml is empty
RUN if [ -s /app/conda/environment.yml ]; then \
    conda env update -n base -f /app/conda/environment.yml; \
    else \
    echo "Skipping conda env update - environment.yml is empty"; \
    fi

# Install psycopg2-binary separately to avoid conflicts
RUN pip install psycopg2-binary

RUN conda clean --all

WORKDIR /app

# Entrypoint is set in docker-compose.yml for flexibility
# Default CMD for production use
CMD ["/entrypoint.sh"]