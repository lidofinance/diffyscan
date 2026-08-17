# uv binary from Astral's official image, the same vendor that ships the uv wheel on PyPI.
# A literal FROM stage (pinned by digest, tag kept) so Dependabot's docker ecosystem bumps it.
# COPY --from below copies only the static /uv and /uvx binaries; the OS layers stay out.
# BuildKit attaches build provenance and an SBOM as attestation manifests; verify with:
#   gh attestation verify oci://ghcr.io/astral-sh/uv:<version> --owner astral-sh
FROM ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc AS uv

FROM mcr.microsoft.com/devcontainers/python:3.14@sha256:f04a1e9c29e371436d6086908eed22ac0ba087bae0f8edb826838283cf3d1726

COPY --from=uv /uv /uvx /bin/

RUN uv --version
