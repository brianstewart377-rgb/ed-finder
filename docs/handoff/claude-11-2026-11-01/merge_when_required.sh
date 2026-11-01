#!/bin/bash
# Update PR branch to main, wait for the branch-protection REQUIRED checks on the
# new head, post the acceptance note, then squash-merge at that exact head.
# Repeats (max 4 tries) when another merge makes it behind again.
# Usage: merge_when_required.sh PR "commit title" acceptance.md
R=repos/brianstewart377-rgb/ed-finder; PR=$1; TITLE=$2; NOTE=$3
mapfile -t REQ < <(gh api $R/branches/main/protection/required_status_checks --jq '.contexts[]')
for try in 1 2 3 4; do
  head=$(gh api $R/pulls/$PR --jq .head.sha)
  behind=$(gh api $R/compare/main...$head --jq .behind_by)
  if [ "$behind" != 0 ]; then
    gh api -X PUT $R/pulls/$PR/update-branch -f expected_head_sha=$head --jq .message
    for i in $(seq 1 30); do sleep 10; new=$(gh api $R/pulls/$PR --jq .head.sha); [ "$new" != "$head" ] && break; done
    head=$new
  fi
  echo "try $try head=$head"
  ok=0
  for i in $(seq 1 120); do
    sleep 30
    states=$(gh api --paginate "$R/commits/$head/check-runs?per_page=100" --jq '.check_runs[]|"\(.name)\t\(.status)\t\(.conclusion)"')
    pending=0; failed=""
    for c in "${REQ[@]}"; do
      line=$(printf '%s\n' "$states" | awk -F'\t' -v n="$c" '$1==n' | tail -1)
      st=$(cut -f2 <<<"$line"); co=$(cut -f3 <<<"$line")
      if [ -z "$line" ] || [ "$st" != completed ]; then pending=1
      elif [ "$co" != success ] && [ "$co" != skipped ] && [ "$co" != neutral ]; then failed="$failed $c=$co"; fi
    done
    [ -n "$failed" ] && { echo "REQUIRED FAILED:$failed"; exit 1; }
    [ $pending = 0 ] && { ok=1; break; }
    [ "$(gh api $R/compare/main...$head --jq .behind_by)" != 0 ] && { echo "behind again while waiting"; break; }
  done
  [ $ok = 1 ] || continue
  [ "$(gh api $R/compare/main...$head --jq .behind_by)" != 0 ] && { echo "behind again before merge"; continue; }
  sed "s/{HEAD}/${head:0:8}/g" "$NOTE" > /tmp/merge_note_$PR.md
  gh api -X POST $R/issues/$PR/comments -F body=@/tmp/merge_note_$PR.md --jq .html_url
  gh api -X PUT $R/pulls/$PR/merge -f sha=$head -f merge_method=squash -f commit_title="$TITLE (#$PR)" --jq '"MERGED \(.merged) \(.sha)"' && exit 0
  echo "merge call failed; retrying"
done
echo "GAVE UP after 4 tries"; exit 1
