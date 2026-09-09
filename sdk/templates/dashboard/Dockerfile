# Supply an operator-approved digest-pinned Node runtime; no permissive default.
ARG APPROVED_NODE_IMAGE
FROM ${APPROVED_NODE_IMAGE}
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY --chown=65532:65532 dist/ ./dist/
COPY --chown=65532:65532 server.mjs dreamcatcher.json ./
USER 65532:65532
ENV NODE_ENV=production DC_ENV=production PORT=8080
EXPOSE 8080
CMD ["node", "server.mjs"]
