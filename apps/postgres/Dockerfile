FROM postgres:16-bookworm

# Keep pg_repack available across container recreation. The extension's SQL
# objects still live in each database; this image provides the matching server
# library and CLI that CREATE EXTENSION / pg_repack require.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-repack \
    && rm -rf /var/lib/apt/lists/* \
    && pg_repack --version
