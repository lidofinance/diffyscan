# uv binary from Astral's official image, the same vendor that ships the uv wheel on PyPI.
# A literal FROM stage (pinned by digest, tag kept) so Dependabot's docker ecosystem bumps it.
# COPY --from below copies only the static /uv and /uvx binaries; the OS layers stay out.
# BuildKit attaches build provenance and an SBOM as attestation manifests; verify with:
#   gh attestation verify oci://ghcr.io/astral-sh/uv:<version> --owner astral-sh
FROM ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 AS uv

FROM mcr.microsoft.com/devcontainers/python:3.14@sha256:66af9ee0a89e76f83b5c54a0cfdc19966ec8e443e294707f8f9b45f465b42cf1

COPY --from=uv /uv /uvx /bin/

RUN uv --version
