# https://micromamba-docker.readthedocs.io/en/latest/quick_start.html#running-commands-in-dockerfile-within-the-conda-environment

FROM ghcr.io/mamba-org/micromamba

# Copy the necessary files
COPY --chown=$MAMBA_USER:$MAMBA_USER python/conda_env_ctsm_py.yml /tmp/python/env.yaml
COPY --chown=$MAMBA_USER:$MAMBA_USER doc/ctsm-docs_container/requirements.txt /tmp/doc/ctsm-docs_container/requirements.txt

# Install the environment, using the name "base"
RUN micromamba install -y -n base -f /tmp/python/env.yaml && \
    micromamba clean --all --yes

# Activate the environment by default
SHELL ["/bin/bash", "-c"]
ENV MAMBA_DOCKERFILE_ACTIVATE=1
ENV CONDA_DEFAULT_ENV=base

# Set the directory the container should start in
WORKDIR "/home/mambauser"

# The first thing that will happen upon starting the container is to start
# a bash shell with the base environment activated
ENTRYPOINT ["micromamba", "run", "-n", "base"]
