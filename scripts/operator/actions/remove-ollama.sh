#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="ed-finder-prod"
EXPECTED_FQDN="nb79a3d.mevnode.com"

short_host="$(hostname | cut -d. -f1)"
fqdn="$(hostname -f 2>/dev/null || true)"
if [ "$short_host" != "$EXPECTED_HOST" ] || [ "$fqdn" != "$EXPECTED_FQDN" ]; then
  echo '{"operation":"remove-ollama","status":"stopped","failure":"unexpected_host_identity"}'
  exit 1
fi

if [ "$(pwd -P)" != "/opt/ed-finder" ]; then
  echo '{"operation":"remove-ollama","status":"stopped","failure":"unexpected_working_directory"}'
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=()
elif sudo -n true >/dev/null 2>&1; then
  SUDO=(sudo -n)
else
  echo '{"operation":"remove-ollama","status":"stopped","failure":"root_privilege_unavailable"}'
  exit 1
fi

before_avail="$(df -B1 --output=avail / | tail -1 | tr -d ' ')"
removed_paths=0
removed_containers=0
removed_images=0
service_touched=false

# Stop and disable the exact host-managed Ollama service first.
if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files --type=service 2>/dev/null | awk '{print $1}' | grep -qx 'ollama.service' || systemctl is-active --quiet ollama.service 2>/dev/null; then
    "${SUDO[@]}" systemctl stop ollama.service || true
    "${SUDO[@]}" systemctl disable ollama.service || true
    service_touched=true
  fi
fi

# Remove any Docker container/image whose name or image explicitly identifies Ollama.
if command -v docker >/dev/null 2>&1; then
  while IFS=$'\t' read -r cid cname cimage; do
    [ -n "$cid" ] || continue
    lname="${cname,,}"
    limage="${cimage,,}"
    if [[ "$lname" == "ollama" || "$lname" == ollama-* || "$limage" == ollama/* || "$limage" == *"/ollama:"* ]]; then
      "${SUDO[@]}" docker rm -f "$cid" >/dev/null
      removed_containers=$((removed_containers + 1))
    fi
  done < <(docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Image}}' 2>/dev/null || "${SUDO[@]}" docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Image}}')

  while IFS=$'\t' read -r iid iref; do
    [ -n "$iid" ] || continue
    lref="${iref,,}"
    if [[ "$lref" == ollama/* || "$lref" == *"/ollama:"* ]]; then
      "${SUDO[@]}" docker image rm -f "$iid" >/dev/null 2>&1 || true
      removed_images=$((removed_images + 1))
    fi
  done < <(docker image ls --format '{{.ID}}\t{{.Repository}}:{{.Tag}}' 2>/dev/null || "${SUDO[@]}" docker image ls --format '{{.ID}}\t{{.Repository}}:{{.Tag}}')
fi

# Purge only the exact package if a distro package was used. Do not autoremove unrelated dependencies.
if command -v dpkg-query >/dev/null 2>&1 && dpkg-query -W -f='${Status}' ollama 2>/dev/null | grep -q 'install ok installed'; then
  "${SUDO[@]}" env DEBIAN_FRONTEND=noninteractive apt-get purge -y ollama >/dev/null
fi
if command -v snap >/dev/null 2>&1 && snap list ollama >/dev/null 2>&1; then
  "${SUDO[@]}" snap remove ollama >/dev/null
fi

# Exact Ollama service/binary/library/model/cache locations used by the official installer
# and common Linux deployments. No broad wildcard deletion is permitted.
paths=(
  /etc/systemd/system/ollama.service
  /etc/systemd/system/multi-user.target.wants/ollama.service
  /etc/systemd/system/default.target.wants/ollama.service
  /lib/systemd/system/ollama.service
  /usr/lib/systemd/system/ollama.service
  /usr/local/bin/ollama
  /usr/bin/ollama
  /usr/local/lib/ollama
  /usr/local/share/ollama
  /usr/share/ollama/.ollama
  /usr/share/ollama
  /var/lib/ollama
  /root/.ollama
  /home/ollama/.ollama
  /home/ollama
)
for p in "${paths[@]}"; do
  if "${SUDO[@]}" test -e "$p" || "${SUDO[@]}" test -L "$p"; then
    "${SUDO[@]}" rm -rf -- "$p"
    removed_paths=$((removed_paths + 1))
  fi
done

if command -v systemctl >/dev/null 2>&1; then
  "${SUDO[@]}" systemctl daemon-reload || true
  "${SUDO[@]}" systemctl reset-failed ollama.service >/dev/null 2>&1 || true
fi

# Remove the dedicated service account after its data is gone.
if getent passwd ollama >/dev/null 2>&1; then
  "${SUDO[@]}" userdel ollama >/dev/null 2>&1 || true
fi
if getent group ollama >/dev/null 2>&1; then
  "${SUDO[@]}" groupdel ollama >/dev/null 2>&1 || true
fi

# Fail closed if any Ollama executable/service/container or known model directory survives.
failures=()
if command -v ollama >/dev/null 2>&1; then failures+=("ollama_executable_still_present"); fi
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet ollama.service 2>/dev/null; then failures+=("ollama_service_still_active"); fi
if command -v docker >/dev/null 2>&1; then
  if (docker ps -a --format '{{.Names}}\t{{.Image}}' 2>/dev/null || "${SUDO[@]}" docker ps -a --format '{{.Names}}\t{{.Image}}') | grep -i 'ollama' >/dev/null 2>&1; then
    failures+=("ollama_container_still_present")
  fi
fi
for p in /usr/local/lib/ollama /usr/local/share/ollama /usr/share/ollama /var/lib/ollama /root/.ollama /home/ollama; do
  if "${SUDO[@]}" test -e "$p"; then failures+=("ollama_data_still_present:$p"); fi
done

after_avail="$(df -B1 --output=avail / | tail -1 | tr -d ' ')"
freed=$((after_avail - before_avail))

python3 - "$freed" "$removed_paths" "$removed_containers" "$removed_images" "$service_touched" "${failures[*]-}" <<'PY'
import json
import sys
freed, paths, containers, images, service_touched, failures = sys.argv[1:]
items = [x for x in failures.split() if x]
print(json.dumps({
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "remove-ollama",
    "status": "success" if not items else "stopped",
    "host": "ed-finder-prod",
    "freed_root_bytes_estimate": max(0, int(freed)),
    "removed_path_count": int(paths),
    "removed_container_count": int(containers),
    "removed_image_count": int(images),
    "ollama_service_changes_performed": service_touched == "true",
    "failures": items,
    "direct_db_access_performed": False,
    "db_writes_performed": False,
    "migrations_performed": False,
    "application_service_changes_performed": False,
}, sort_keys=True, separators=(",", ":")))
sys.exit(0 if not items else 1)
PY
