# Source-only contract fixture, not a production image.
# WORK-CONNECT: isolated-build. Replace with your approved digest-pinned base.
ARG APPROVED_RUNTIME_IMAGE
FROM ${APPROVED_RUNTIME_IMAGE}
WORKDIR /app
COPY --chown=65532:65532 dist/ ./dist/
USER 65532:65532
ENV PORT=8080
EXPOSE 8080
# Approved base must implement dc-http/v1, including SPA fallback and health checks.
