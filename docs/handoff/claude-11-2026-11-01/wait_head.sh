#!/bin/bash
# Wait until all check runs on SHA complete and Codex's summary shows a completed review of SHA.
R=repos/brianstewart377-rgb/ed-finder; PR=$1; SHA=$2
for i in $(seq 1 120); do
  pending=$(gh api "$R/commits/$SHA/check-runs?per_page=100" --jq '[.check_runs[] | select(.status!="completed")] | length' 2>/dev/null)
  total=$(gh api "$R/commits/$SHA/check-runs?per_page=100" --jq '.check_runs | length' 2>/dev/null)
  cx=$(gh api --paginate "$R/issues/$PR/comments?per_page=100" --jq '[.[] | select(.user.login=="chatgpt-codex-connector[bot]") | .body | capture("codex-review-state:v1 (?<j>\\{.*\\}) -->").j | fromjson | .code_review | "\(.commit_sha) \(.status) \(.has_any_findings)"] | last' 2>/dev/null)
  if [ "$pending" = "0" ] && [ "${total:-0}" -gt 20 ] && [[ "$cx" == "$SHA completed"* ]]; then break; fi
  sleep 30
done
echo "pending=$pending total=$total codex=[$cx]"
gh api "$R/commits/$SHA/check-runs?per_page=100" --jq '.check_runs[] | "\(.name) | \(.conclusion)"' | sort
gh api --paginate "$R/issues/$PR/comments?per_page=100" --jq '.[] | select(.user.login=="chatgpt-codex-connector[bot]" and (.body|test("receipt"))) | "RECEIPT: \(.body[0:300])"' | tail -2
gh api --paginate "$R/pulls/$PR/comments?per_page=100" --jq '.[] | "INLINE \(.path):\(.line) \(.user.login) \(.commit_id[0:8]): \(.body)"'
gh api --paginate "$R/pulls/$PR/reviews?per_page=100" --jq '.[] | "REVIEW \(.user.login) \(.state) \(.commit_id[0:8]): \(.body[0:500])"'
