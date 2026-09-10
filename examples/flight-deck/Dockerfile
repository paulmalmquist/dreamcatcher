# This complete example is assembled with the repo's locked React/Vite and SDK
# by tests/e2e/story.py. WORK-CONNECT: replace this lab base with an approved digest.
ARG APPROVED_NODE_IMAGE
FROM ${APPROVED_NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY sdk sdk
COPY frontend/package.json frontend/package.json
RUN npm ci --ignore-scripts
COPY src src
COPY index.html build.mjs server.mjs dreamcatcher.json ./
RUN node build.mjs
FROM ${APPROVED_NODE_IMAGE}
WORKDIR /app
COPY --from=build /app/dist dist
COPY --from=build /app/server.mjs /app/dreamcatcher.json ./
COPY --from=build /app/sdk/dist sdk/dist
USER 65532:65532
ENV PORT=8080
EXPOSE 8080
CMD ["node","server.mjs"]
