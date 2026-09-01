# uv binary from Astral's official image, the same vendor that ships the uv wheel on PyPI.
# A literal FROM stage (pinned by digest, tag kept) so Dependabot's docker ecosystem bumps it.
# COPY --from below copies only the static /uv and /uvx binaries; the OS layers stay out.
# BuildKit attaches build provenance and an SBOM as attestation manifests; verify with:
#   gh attestation verify oci://ghcr.io/astral-sh/uv:<version> --owner astral-sh
FROM ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff AS uv

FROM mcr.microsoft.com/devcontainers/python:3.14@sha256:97152d71a6e42cc2f4f39d68fe72a94fc10baeb203700296dd3b2db4cfaaa686

COPY --from=uv /uv /uvx /bin/

RUN uv --version
