# uv binary from Astral's official image, the same vendor that ships the uv wheel on PyPI.
# A literal FROM stage (pinned by digest, tag kept) so Dependabot's docker ecosystem bumps it.
# COPY --from below copies only the static /uv and /uvx binaries; the OS layers stay out.
# BuildKit attaches build provenance and an SBOM as attestation manifests; verify with:
#   gh attestation verify oci://ghcr.io/astral-sh/uv:<version> --owner astral-sh
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

FROM mcr.microsoft.com/devcontainers/python:3.15@sha256:0ae003ea761a00b8f8809cfdd08a04edfb1c7f17e76c413b27882ce5939a65f4

COPY --from=uv /uv /uvx /bin/

RUN uv --version
