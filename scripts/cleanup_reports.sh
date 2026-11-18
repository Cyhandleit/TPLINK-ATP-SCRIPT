#!/bin/bash
# TP-Link ATP reports disk cleanup policy (P2-1)
# Purpose: periodically clean up outdated ATP_* report directories under reports/, keep only the most recent N, preventing unbounded disk growth.
#
# Suggest running on host cron (e.g. every Sunday 03:00):
#   0 3 * * 0 /root/Repos/github.com/Cyhandleit/TPLINK-ATP-SCRIPT/scripts/cleanup_reports.sh >> /var/log/atp-cleanup.log 2>&1
#
# Environment variables:
#   ATP_REPORTS_DIR   report root directory (default ./reports, relative to the reports/ one level up from this script's directory)
#   ATP_REPORT_KEEP   number of recent reports to keep (default 30)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS_DIR="${ATP_REPORTS_DIR:-$REPO_DIR/reports}"
KEEP="${ATP_REPORT_KEEP:-30}"

if [[ ! -d "$REPORTS_DIR" ]]; then
  echo "[cleanup] reports directory does not exist: $REPORTS_DIR, skip"
  exit 0
fi

# Sort ATP_* directories by modification time descending, skip the first KEEP, delete the rest
mapfile -t DIRS < <(find "$REPORTS_DIR" -maxdepth 1 -type d -name 'ATP_*' -printf '%T@ %p\n' \
  | sort -rn \
  | awk '{print $2}')

deleted=0
for ((i=KEEP; i < ${#DIRS[@]}; i++)); do
  if [[ -d "${DIRS[$i]}" ]]; then
    rm -rf "${DIRS[$i]}"
    echo "[cleanup] deleted expired report: ${DIRS[$i]}"
    deleted=$((deleted + 1))
  fi
done

echo "[cleanup] done: kept recent $KEEP, deleted $deleted expired reports"
