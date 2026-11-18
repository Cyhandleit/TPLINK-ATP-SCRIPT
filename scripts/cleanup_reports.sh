#!/bin/bash
# TP-Link ATP reports 磁盘清理策略（P2-1）
# 用途：定期清理 reports/ 下过旧的 ATP_* 报告目录，仅保留最近 N 份，防止磁盘无限增长。
#
# 建议以宿主机 cron 运行（例如每周日 03:00）：
#   0 3 * * 0 /root/Repos/github.com/Cyhandleit/TPLINK-ATP-SCRIPT/scripts/cleanup_reports.sh >> /var/log/atp-cleanup.log 2>&1
#
# 环境变量：
#   ATP_REPORTS_DIR   报告根目录（默认 ./reports，相对本脚本所在目录的上一级 reports/）
#   ATP_REPORT_KEEP   保留最近多少份报告（默认 30）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS_DIR="${ATP_REPORTS_DIR:-$REPO_DIR/reports}"
KEEP="${ATP_REPORT_KEEP:-30}"

if [[ ! -d "$REPORTS_DIR" ]]; then
  echo "[cleanup] reports 目录不存在: $REPORTS_DIR，跳过"
  exit 0
fi

# 按修改时间倒序排列 ATP_* 目录，跳过前 KEEP 份，其余删除
mapfile -t DIRS < <(find "$REPORTS_DIR" -maxdepth 1 -type d -name 'ATP_*' -printf '%T@ %p\n' \
  | sort -rn \
  | awk '{print $2}')

deleted=0
for ((i=KEEP; i < ${#DIRS[@]}; i++)); do
  if [[ -d "${DIRS[$i]}" ]]; then
    rm -rf "${DIRS[$i]}"
    echo "[cleanup] 已删除过期报告: ${DIRS[$i]}"
    deleted=$((deleted + 1))
  fi
done

echo "[cleanup] 完成：保留最近 $KEEP 份，删除了 $deleted 份过期报告"
