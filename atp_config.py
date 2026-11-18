"""TP-Link ATP 配置管理：环境变量 > config.json，无硬编码密码默认值。"""
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")

SENSITIVE_KEYS = {
    "admin_pass", "superadmin_pass", "tauc_pass",
    "wifi_24g_pass", "wifi_5g_pass", "wifi_6g_pass",
    "wifi_guest_pass", "wifi_mlo_pass",
}

def _env(key, default=None):
    return os.environ.get(key, default)

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
