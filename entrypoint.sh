#!/bin/sh
set -e

# 入口脚本：按环境变量决定 Flask 调试开关（生产默认关闭，修复 SEC-03）
#   ATP_DEBUG=1  -> 开启 debug（仅开发/排障，不建议生产使用）
#   其余         -> 保持 debug=False
if [ "${ATP_DEBUG:-0}" = "1" ]; then
  sed -i 's/debug=False/debug=True/' atp_web.py
fi

exec "$@"
