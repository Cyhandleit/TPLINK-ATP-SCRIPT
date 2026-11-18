"""TP-Link ATP Config Management: environment variables > config.json, no hardcoded password defaults.

Public interface (compatible with atp_web.py, signatures unchanged):
    DEFAULT_CONFIG, load_config(), save_config(cfg), sanitize_config(cfg)

New:
    validate_config(cfg)              # config validity check, raises ValueError on failure
    load_api_key() / api_key_enabled() / validate_api_key(key)  # API Key auth helpers
    export_config(cfg) / import_config(source)                  # config import/export (JSON)
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

# ping_seconds allowed range (seconds)
PING_SECONDS_MIN = 1
PING_SECONDS_MAX = 3600

# Required config items: validate_config raises error if missing or empty
REQUIRED_KEYS = ("admin_pass", "superadmin_pass")


def _env(key: str, default: str | None = None) -> str:
    """Read environment variable, always return str (avoid LSP None warnings for int()/lower())."""
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
        except Exception:  # nosec B110
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
# Config validation
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
    """Validate config validity, raises ValueError on failure (includes all issues, not just the first).

    Rules:
        - gateway_ip must be a valid IPv4 address
        - admin_pass / superadmin_pass required and non-empty
        - ping_seconds must be an integer between 1 and 3600 seconds
    """
    if not isinstance(cfg, dict):
        raise ValueError("Config must be a dictionary")

    errors: list[str] = []

    gateway_ip = cfg.get("gateway_ip")
    if not _is_valid_ipv4(gateway_ip):
        errors.append("gateway_ip: must be a valid IPv4 address")

    for key in REQUIRED_KEYS:
        if not cfg.get(key):
            errors.append(f"{key}: required field, missing or empty")

    ping = cfg.get("ping_seconds")
    try:
        ping_int = int(ping)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        errors.append("ping_seconds: must be an integer")
        ping_int = None
    if ping_int is not None and not (PING_SECONDS_MIN <= ping_int <= PING_SECONDS_MAX):
        errors.append(f"ping_seconds: must be between {PING_SECONDS_MIN} and {PING_SECONDS_MAX} seconds")

    if errors:
        raise ValueError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# API Key auth helper (auxiliary only, not bound to any web framework)
# ---------------------------------------------------------------------------

def load_api_key() -> str | None:
    """Read API Key from environment variable ATP_API_KEY; returns None if not set (auth not enabled)."""
    key = _env(API_KEY_ENV)
    return key or None


def api_key_enabled() -> bool:
    """Whether API Key auth is enabled (returns False if ATP_API_KEY not set)."""
    return bool(load_api_key())


def validate_api_key(key: str | None) -> bool:
    """Validate the API Key sent by the client.

    If ATP_API_KEY is not configured, passes directly (auth not enabled);
    if configured, uses constant-time comparison to avoid timing attacks.
    """
    expected = load_api_key()
    if not expected:
        return True
    if not key:
        return False
    return hmac.compare_digest(key, expected)


def unauthorized_payload() -> dict:
    """Standard response body returned when unauthenticated (for Web layer to use with 401 status code)."""
    return {"ok": False, "error": "unauthorized", "message": "API Key authentication required"}


# ---------------------------------------------------------------------------
# Config import/export (JSON)
# ---------------------------------------------------------------------------

def export_config(cfg) -> str:
    """Serialize config dictionary to JSON string (can be written to file or transmitted over network)."""
    return json.dumps(cfg, ensure_ascii=False, indent=2)


def export_config_file(cfg, path: str) -> str:
    """Write config to JSON file, return file path."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(export_config(cfg))
    return path


def import_config(source: str) -> dict:
    """Import config from JSON.

    source can be a JSON string or an existing JSON file path;
    returns the parsed config dictionary (does not merge DEFAULT_CONFIG, does not auto-validate;
    call validate_config yourself if needed).
    """
    if os.path.isfile(source):
        with open(source, encoding="utf-8") as f:
            text = f.read()
    else:
        text = source
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Imported config must be a JSON object")
    return data
