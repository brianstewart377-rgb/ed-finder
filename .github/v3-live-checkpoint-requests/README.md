# V3 live-checkpoint prerequisite requests

After this control plane is merged, an operator may dispatch it through the
Actions API or merge exactly one request file here on `main`:

```json
{"operation":"check"}
```

or, after approving the `v3-live-checkpoint` environment:

```json
{"operation":"provision"}
```

The request selects only the fixed `check` or `provision` operation. It cannot
choose a host, command, path, image, database, Git ref, or production target.
Provisioning emits sanitized evidence artifacts; it never edits or pushes the
committed `target-authority.json`.
