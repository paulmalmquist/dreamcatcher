FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package*.json ./
COPY frontend/package.json frontend/package.json
COPY sdk/package.json sdk/package.json
RUN npm ci --ignore-scripts
COPY frontend frontend
COPY sdk sdk
COPY scripts/package-sdk.mjs scripts/package-sdk.mjs
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home dreamcatcher
COPY backend backend
COPY scripts/run.py scripts/run.py
COPY --from=web /app/frontend/dist frontend/dist
COPY --from=web /app/artifacts artifacts
RUN mkdir /app/data && chown 10001:10001 /app/data
USER 10001
ENV DC_BIND_HOST=0.0.0.0
EXPOSE 8000
CMD ["python","scripts/run.py"]
