ARG DEVCONTAINER_BASE_IMAGE=mcr.microsoft.com/devcontainers/python:3.11@sha256:f46978552419eb3cbf3bcf662ba0dca1639b07307f64447a3fcbe46110710b27
FROM ${DEVCONTAINER_BASE_IMAGE}

ARG UV_VERSION=0.10.9

RUN python -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --only-binary=:all: \
    "uv==${UV_VERSION}" \
    && python -m uv --version
