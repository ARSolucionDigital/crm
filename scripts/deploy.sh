#!/usr/bin/env bash
set -Eeuo pipefail

workflow="${1:-twenty}"
case "$workflow" in
  twenty) workflow_file="deploy-twenty.yml" ;;
  bookstack) workflow_file="deploy-bookstack.yml" ;;
  *) echo "Usage: $0 [twenty|bookstack]" >&2; exit 2 ;;
esac

command -v gh >/dev/null || { echo "GitHub CLI (gh) is required to dispatch deployments" >&2; exit 1; }
branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || { echo "Deployments must be dispatched from main (current: $branch)" >&2; exit 1; }
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean; commit and review changes before deploying." >&2
  git status --short >&2
  exit 1
fi

echo "Dispatching $workflow_file from $branch. CI builds, backs up, health-checks, and records rollback state."
gh workflow run "$workflow_file" --ref "$branch"
