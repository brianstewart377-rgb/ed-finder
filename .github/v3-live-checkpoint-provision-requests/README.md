# V3 live-checkpoint provisioning requests

This directory is the allowlisted request surface for the separate
non-production Contabo provisioning workflow. Request commits belong only on
the dedicated `v3-live-checkpoint-provision-requests` branch and contain
exactly one changed JSON file.

The document has exactly three string fields:

```json
{
  "operation": "provision-infrastructure",
  "backend_image": "",
  "web_image": ""
}
```

Leave both image fields empty to emit the explicit secret-backed GHCR blocker.
To prove anonymous public pulls, provide both canonical digest-pinned V3 image
references. Requests cannot supply credentials, hosts, paths, commands, or a
deployment/release operation.
