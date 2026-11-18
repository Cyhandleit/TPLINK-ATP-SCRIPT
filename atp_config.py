"""TP-Link ATP 配置管理：环境变量 > config.json，无硬编码密码默认值。

公开接口（与 atp_web.py 兼容，签名不变）：
    DEFAULT_CONFIG, load_config(), save_config(cfg), sanitize_config(cfg)

新增：
    validate_config(cfg)              # 配置合法性校验，失败抛出 ValueError
    load_api_key() / api_key_enabled() / validate_api_key(key)  # API Key 认证辅助
    export_config(cfg) / import_config(source)                  # 配置导入/导出（JSON）
"""

import hmac
import ipaddress
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")

SENSITIVE_KEYS = {
    "admin_pass", "superadmin_pass", "tauc_pass",
    "wifi_24g_pass", "wifi_5g_pass", "wifi_6g_pass",
    "wifi_guest_pass", "wifi_mlo_pass",
}

API_KEY_ENV = "ATP_API_KEY"

# ping_seconds 允许范围（秒）
PING_SECONDS_MIN = 1
PING_SECONDS_MAX = 3600

# 必填配置项：缺失或为空时 validate_config 会报错
REQUIRED_KEYS = ("admin_pass", "superadmin_pass")


def _env(key: str, default: str | None = None) -> str:
    """读取环境变量，始终返回 str（避免 LSP 对 int()/lower() 的 None 警告）。"""
    value = os.environ.get(key, default)
    return value if value is not None else ""


DEFAULT_CONFIG = {
    "gateway_ip": _env("ATP_GATEWAY_IP", "192.168.1.1"),
    "gateway_scheme": _env("ATP_GATEWAY_SCHEME", "http"),
    "admin_user": _env("ATP_ADMIN_USER", "admin"),
    "admin_pass": _env("ATP_ADMIN_PASS", ""),
    "superadmin_user": _env("ATP_SUPERADMIN_USER", "superadmin"),
    "superadmin_pass": _env("ATP_SUPERADMIN_PASS", ""),
    "lan_iface": _env("ATP_LAN_IFACE", "eth0"),
    "wifi_iface": _env("ATP_WIFI_IFACE", "wlan0"),
    "ext_nic_ip": _env("ATP_EXT_NIC_IP", ""),
    "iperf3_server_ip": _env("ATP_IPERF3_SERVER_IP", "192.168.1.100"),
    "http_forward_port": int(_env("ATP_HTTP_FORWARD_PORT", "30000")),
    "firmware_bin_path": _env("ATP_FIRMWARE_BIN_PATH", "./firmware_new.bin"),
    "acs_api_url": _env("ATP_ACS_API_URL", "http://192.168.1.200:7557"),
    "acs_device_id": _env("ATP_ACS_DEVICE_ID", "001122-EX820v-SN12345678"),
    "tauc_url": _env("ATP_TAUC_URL", "https://tauc.tp-link.com"),
    "tauc_user": _env("ATP_TAUC_USER", "tauc_tester@example.com"),
    "tauc_pass": _env("ATP_TAUC_PASS", ""),
    "ping_seconds": int(_env("ATP_PING_SECONDS", "300")),
    "run_destructive": _env("ATP_RUN_DESTRUCTIVE", "false").lower() == "true",
    "headed": _env("ATP_HEADED", "false").lower() == "true",
    "sensitive_regions": {},
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def sanitize_config(cfg):
    out = dict(cfg)
    for k in SENSITIVE_KEYS:
        if k in out and out[k]:
            out[k] = "***"
    return out


# ---------------------------------------------------------------------------
# 配置验证
# ---------------------------------------------------------------------------

def _is_valid_ipv4(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


def validate_config(cfg) -> None:
    """校验配置合法性，失败抛出 ValueError（包含所有问题，不只第一个）。

    规则：
        - gateway_ip 必须是合法的 IPv4 地址
        - admin_pass / superadmin_pass 必填且非空
        - ping_seconds 必须是整数且在 1 ~ 3600 秒之间
    """
    if not isinstance(cfg, dict):
        raise ValueError("配置必须是字典")

    errors: list[str] = []

    gateway_ip = cfg.get("gateway_ip")
    if not _is_valid_ipv4(gateway_ip):
        errors.append("gateway_ip: 必须是合法的 IPv4 地址")

    for key in REQUIRED_KEYS:
        if not cfg.get(key):
            errors.append(f"{key}: 必填项，缺失或为空")

    ping = cfg.get("ping_seconds")
    try:
        ping_int = int(ping)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        errors.append("ping_seconds: 必须是整数")
        ping_int = None
    if ping_int is not None and not (PING_SECONDS_MIN <= ping_int <= PING_SECONDS_MAX):
        errors.append(f"ping_seconds: 必须在 {PING_SECONDS_MIN} ~ {PING_SECONDS_MAX} 秒之间")

    if errors:
        raise ValueError("配置验证失败：\n" + "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# API Key 认证辅助（仅辅助判断，不绑定任何 Web 框架）
# ---------------------------------------------------------------------------

def load_api_key() -> str | None:
    """从环境变量 ATP_API_KEY 读取 API Key；未设置返回 None（认证不启用）。"""
    key = _env(API_KEY_ENV)
    return key or None


def api_key_enabled() -> bool:
    """是否启用 API Key 认证（未设置 ATP_API_KEY 时返回 False）。"""
    return bool(load_api_key())


def validate_api_key(key: str | None) -> bool:
    """校验客户端传来的 API Key。

    未配置 ATP_API_KEY 时直接通过（认证未启用）；
    已配置时使用恒时比对，避免时序攻击。
    """
    expected = load_api_key()
    if not expected:
        return True
    if not key:
        return False
    return hmac.compare_digest(key, expected)


def unauthorized_payload() -> dict:
    """未认证时返回的标准响应体（供 Web 层配合 401 状态码使用）。"""
    return {"ok": False, "error": "unauthorized", "message": "需要 API Key 认证"}


# ---------------------------------------------------------------------------
# 配置导入/导出（JSON）
# ---------------------------------------------------------------------------

def export_config(cfg) -> str:
    """将配置字典序列化为 JSON 字符串（可直接写入文件或通过网络传输）。"""
    return json.dumps(cfg, ensure_ascii=False, indent=2)


def export_config_file(cfg, path: str) -> str:
    """将配置写入 JSON 文件，返回文件路径。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(export_config(cfg))
    return path


def import_config(source: str) -> dict:
    """从 JSON 导入配置。

    source 可以是 JSON 字符串，也可以是存在的 JSON 文件路径；
    返回解析后的配置字典（不合并 DEFAULT_CONFIG，也不自动校验，
    如需请自行调用 validate_config）。
    """
    if os.path.isfile(source):
        with open(source, encoding="utf-8") as f:
            text = f.read()
    else:
        text = source
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("导入的配置必须是 JSON 对象")
    return data
