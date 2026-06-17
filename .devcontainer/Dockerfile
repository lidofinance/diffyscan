ARG DEVCONTAINER_BASE_IMAGE=mcr.microsoft.com/devcontainers/python:3.11@sha256:f46978552419eb3cbf3bcf662ba0dca1639b07307f64447a3fcbe46110710b27
FROM ${DEVCONTAINER_BASE_IMAGE}

# uv binary from Astral's official image, the same vendor that ships the uv wheel on PyPI.
# Pinned by digest; the tag stays so Dependabot bumps both together.
# COPY --from copies only the static /uv and /uvx binaries; the OS layers stay out.
# BuildKit attaches build provenance and an SBOM as attestation manifests; verify with:
#   gh attestation verify oci://ghcr.io/astral-sh/uv:0.10.9 --owner astral-sh
COPY --from=ghcr.io/astral-sh/uv:0.10.9@sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82 /uv /uvx /bin/

RUN uv --version
