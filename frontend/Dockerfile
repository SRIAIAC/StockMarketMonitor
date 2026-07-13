FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# Vite bakes VITE_* vars into the built JS at build time (not read at
# container startup) — must be passed as a build arg, e.g.
# `docker build --build-arg VITE_API_BASE_URL=https://backend-xyz.a.run.app`.
# Required whenever frontend/backend don't share a hostname+port (Cloud Run,
# ECS, Azure Container Apps all give each service its own URL).
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM node:20-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist
EXPOSE 5173
# Shell form so $PORT gets expanded — Cloud Run injects its own PORT
# (usually 8080); falls back to 5173 for local docker-compose.
CMD serve -s dist -l ${PORT:-5173}
