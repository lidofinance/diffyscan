ARG DEVCONTAINER_BASE_IMAGE=mcr.microsoft.com/devcontainers/python:3.14@sha256:1af48f9bd555f7972b14424def113c166dab9c5027bd9d9f5cc57704a42974f2
FROM ${DEVCONTAINER_BASE_IMAGE}

ARG UV_VERSION=0.10.9

RUN python -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --only-binary=:all: \
    "uv==${UV_VERSION}" \
    && python -m uv --version
