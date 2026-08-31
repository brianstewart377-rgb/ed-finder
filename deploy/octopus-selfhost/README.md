# Octopus self-host deployment input

This is an isolated preparation package for official Octopus `1.0.122`. It is
not wired into ED-Finder's compose, nginx, databases, migration ledger, or edge
network. Do not run this file from the repository: use the operator script to
install a private copy and generate a mode-0600 environment file.

`octopus.env.template` is a contract fixture, not a usable environment file.
Provider and GitHub App credentials are intentionally absent and must be added
only by the encrypted allowlisted handoff. The installed
`octopus.env` is secret and must never be committed, printed, or attached to an
Actions artifact.

See `docs/operations/octopus-selfhost.md` for the authorised future sequence.
