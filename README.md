# ED Finder — Hetzner Stack

Self-hosted Elite Dangerous colony finder backed by the full 186M-system Spansh dataset on PostgreSQL.

See **[hetzner/README.md](hetzner/README.md)** for the complete setup, import, and operations guide.

## Quick orientation

```
hetzner/
├── backend/          FastAPI API + EDDN listener
├── config/           nginx config, pgBouncer config
├── import/           Post-import scripts (build_grid, build_ratings, build_clusters)
├── sql/              Schema (001_schema.sql, 002_indexes.sql, 003_functions.sql)
├── tests/            Test suite
├── docker-compose.yml
├── setup.sh          First-time server setup
└── README.md         Full documentation
```

## Import script versions

| Script | Version |
|---|---|
| `import_spansh.py` | 2.6 |
| `build_grid.py` | 2.4 |
| `build_ratings.py` | 2.5 |
| `build_clusters.py` | 1.4 |
