#!/usr/bin/env bash
set -euo pipefail
readonly EDGE=ed-nginx
readonly CONFIG=/opt/ed-public-edge/nginx.conf
readonly SNIPPET=/opt/ed-public-edge/conf.d/octopus.conf
die(){ printf 'error: %s\n' "$*" >&2; exit 64; }
case "${1:-}" in
  topology)
    printf 'read_only: true\nedge_container_present: '; docker inspect "$EDGE" >/dev/null 2>&1 && echo true || echo false
    printf 'edge_network_mode: '; docker inspect -f '{{.HostConfig.NetworkMode}}' "$EDGE" 2>/dev/null || echo unavailable
    printf 'edge_config_sha256: '; [[ -f $CONFIG ]] && sha256sum "$CONFIG" | cut -d' ' -f1 || echo unavailable
    printf 'include_contract_present: '; grep -Fxq '    include /opt/ed-public-edge/conf.d/*.conf;' "$CONFIG" 2>/dev/null && echo true || echo false
    printf 'htpasswd_mount_present: '; docker inspect -f '{{range .Mounts}}{{if and (eq .Source "/opt/octopus/ui.htpasswd") (eq .Destination "/etc/nginx/octopus.htpasswd")}}true{{end}}{{end}}' "$EDGE" 2>/dev/null | grep -qx true && echo true || echo false
    ;;
  install)
    [[ $# -eq 2 && $2 =~ ^[a-f0-9]{64}$ ]] || die 'install requires expected config SHA-256'
    [[ -f /opt/octopus/receipts/private-proof ]] || die 'private proof required before public edge route'
    [[ $(docker inspect -f '{{.HostConfig.NetworkMode}}' "$EDGE") == host ]] || die 'edge must use host networking for loopback route'
    [[ $(sha256sum "$CONFIG" | cut -d' ' -f1) == "$2" ]] || die 'edge config fingerprint mismatch'
    grep -Fxq '    include /opt/ed-public-edge/conf.d/*.conf;' "$CONFIG" || die 'expected conf.d include is absent'
    [[ $(docker inspect -f '{{range .Mounts}}{{if and (eq .Source "/opt/octopus/ui.htpasswd") (eq .Destination "/etc/nginx/octopus.htpasswd")}}true{{end}}{{end}}' "$EDGE") == true ]] || die 'expected htpasswd mount is absent'
    [[ ! -e $SNIPPET ]] || die 'Octopus route already exists'
    install -d -m 0755 "$(dirname "$SNIPPET")"; umask 077; tmp=$(mktemp "${SNIPPET}.XXXXXX")
    printf '%s\n' \
      'server { listen 80; server_name octopus.ed-finder.app; location /.well-known/acme-challenge/ { root /var/www/certbot; } location / { return 301 https://$host$request_uri; } }' \
      'server {' '  listen 443 ssl;' '  server_name octopus.ed-finder.app;' \
      '  ssl_certificate /etc/letsencrypt/live/octopus.ed-finder.app/fullchain.pem;' \
      '  ssl_certificate_key /etc/letsencrypt/live/octopus.ed-finder.app/privkey.pem;' \
      '  location = /api/github/webhook { proxy_pass http://127.0.0.1:43300; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; }' \
      '  location / { auth_basic "Octopus"; auth_basic_user_file /etc/nginx/octopus.htpasswd; proxy_pass http://127.0.0.1:43300; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; }' '}' > "$tmp"
    chmod 0644 "$tmp"; mv "$tmp" "$SNIPPET"; docker exec "$EDGE" nginx -t; docker exec "$EDGE" nginx -s reload
    install -d -m 0700 /opt/octopus/receipts; printf 'route=octopus.ed-finder.app\nrollback=remove-snippet-and-reload\n' | install -m 0600 /dev/stdin /opt/octopus/receipts/public-edge-proof
    ;;
  rollback)
    [[ -f $SNIPPET ]] || die 'route is not installed'; mv "$SNIPPET" "${SNIPPET}.disabled"; docker exec "$EDGE" nginx -t; docker exec "$EDGE" nginx -s reload
    rm -f /opt/octopus/receipts/public-edge-proof
    ;;
  *) die 'unsupported edge operation' ;;
esac
