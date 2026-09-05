# syntax=docker/dockerfile:1
FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS build

ARG BUILD_SHA
WORKDIR /workspace/apps/web

RUN case "$BUILD_SHA" in \
      *[!0-9a-f]*|'') exit 64 ;; \
    esac && [ "${#BUILD_SHA}" -eq 40 ]

RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN VITE_BUILD_SHA="$BUILD_SHA" pnpm build

FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de AS runtime

ARG BUILD_SHA
RUN case "$BUILD_SHA" in \
      *[!0-9a-f]*|'') exit 64 ;; \
    esac && [ "${#BUILD_SHA}" -eq 40 ]

COPY apps/web/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY apps/web/nginx/proxy_params /etc/nginx/proxy_params
COPY --from=build /workspace/apps/web/build/ /usr/share/nginx/html/

ENV BUILD_SHA="$BUILD_SHA"
LABEL org.opencontainers.image.revision="$BUILD_SHA"

EXPOSE 8080
