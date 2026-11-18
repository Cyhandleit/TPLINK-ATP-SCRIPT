# TP-Link ATP 自动化测试 — Docker 化基础镜像
# 基于微软官方 Playwright Python 镜像，内置 Chromium 及系统依赖
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# 锁定 Python 依赖，保证构建可复现
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

# 应用代码
COPY atp_engine.py atp_web.py known_issues.md ./

# 生产默认关闭 Flask 调试（修复 SEC-03），可通过 ATP_DEBUG=1 开启
RUN sed -i 's/debug=True/debug=False/' atp_web.py

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    ATP_DEBUG=0

ENTRYPOINT ["/entrypoint.sh"]
# 默认启动 Web UI；CLI 引擎可通过 `docker compose run atp-engine ...` 覆盖 command
CMD ["python", "atp_web.py"]
