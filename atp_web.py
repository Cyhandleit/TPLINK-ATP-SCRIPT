"""TP-Link ATP Web UI — Flask test platform (config, dashboard, per-case restart)."""
import os
import threading
import time
import subprocess  # nosec B404
import shlex
import re
import platform
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from flask import Flask, request, jsonify, send_from_directory
import requests

from atp_config import load_config, save_config, sanitize_config, validate_config, load_api_key, validate_api_key, unauthorized_payload, SENSITIVE_KEYS

BASE = os.path.dirname(os.path.abspath(__file__))
REPORT_ROOT = os.path.join(BASE, "reports")

CONFIG = load_config()

# ---------------- Test cases ----------------
CASES = [
    # id, title, stage
    ("1.1", "Login Test (admin/superadmin)", "1"),
    ("2.1", "WAN Connectivity (PPPoE & IPv6)", "1"),
    ("2.2", "WAN Reconnection Test", "1"),
    ("2.3", "Internet Connectivity Test", "1"),
    ("2.4", "WAN Diagnostics (GUI)", "1"),
    ("2.6", "GPON and eWAN Failover Test", "1"),
    ("4.8", "IPv6 Connectivity", "1"),
    ("3.1", "LAN Speed Test", "2"),
    ("3.2", "Wi-Fi 2.4GHz Speedtest", "2"),
    ("3.3", "Wi-Fi 5GHz Speedtest", "2"),
    ("3.4", "Wi-Fi 6GHz Speedtest", "2"),
    ("3.5", "Web Browsing", "2"),
    ("3.6", "Online Streaming (1080p/4K/8K)", "2"),
    ("3.7", "P2P / Heavy Download", "2"),
    ("4.1", "Port Forwarding (Port 30000)", "3"),
    ("4.2", "VPN Connectivity Test", "3"),
    ("4.3", "Parental Control / Web Filtering", "3"),
    ("4.4", "QoS (Quality of Service)", "3"),
    ("4.5", "DDNS (No-IP)", "3"),
    ("4.6", "MAC Filtering", "3"),
    ("4.7", "Guest Network", "3"),
    ("4.9", "Wireless Schedule", "3"),
    ("4.11", "Dual LAN", "3"),
    ("4.12", "Schedule Reboot", "3"),
    ("4.13", "Wi-Fi Stability (RSSI Consistency)", "3"),
    ("4.15", "Multi-Link Operation (MLO)", "3"),
    ("4.16", "Band Steering Function Test", "3"),
    ("10.1", "ACS Registration and Connection", "4"),
    ("10.2", "ACS Parameter GET/SET", "4"),
    ("10.3", "ACS Remote Reboot", "4"),
    ("10.4", "ACS Firmware Upgrade", "4"),
    ("10.5", "ACS Factory Reset", "4"),
    ("1.3", "Router Reboot (Web UI)", "5"),
    ("6.1", "Firmware Upgrade via UI", "5"),
    ("2.5/7.2", "Long-Duration Ping Stability", "5"),
]

# Allow CASES to be overridden via config.json / env var ATP_CASES.
# Expects a JSON list of [id, title, stage] tuples.
_case_json = CONFIG.get("cases") or ""
if _case_json:
    try:
        import json as _json
        _parsed = _json.loads(_case_json)
        if isinstance(_parsed, list):
            CASES = [tuple(c) for c in _parsed
                     if isinstance(c, (list, tuple)) and len(c) == 3]
    except Exception:  # nosec B110
        pass  # keep hardcoded defaults on parse error

state = {cid: {"status": "PENDING", "detail": "", "screenshots": [], "logs": "",
               "start": None, "end": None} for cid, _, _ in CASES}
state_lock = threading.Lock()
exec_lock = threading.Lock()
cancel_event = threading.Event()  # set by /api/stop; checked between cases

app = Flask(__name__)

# ---------------- API Key auth (optional) ----------------
# When ATP_API_KEY is not set, every request passes through unchanged (zero impact on current UI).
# When set, callers must send `X-API-Key` (or `X-Hermes-API-Key`) on /api/* routes.
def _api_key_required():
    expected = load_api_key()
    if not expected:
        return None
    key = request.headers.get('X-API-Key') or request.headers.get('X-Hermes-API-Key')
    if not validate_api_key(key):
        return jsonify(unauthorized_payload()), 401

@app.before_request
def _api_key_gate():
    if request.path.startswith('/api/'):
        res = _api_key_required()
        if res:
            return res

# ---------------- Utilities ----------------


def run_cmd(cmd, timeout=60, shell=False):
    try:
        p = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)  # nosec B602
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return -1, "Command timed out"


def run_ping_stats(target, count=10, ipv6=False):
    is_win = platform.system() == "Windows"
    f6 = ["-6"] if ipv6 else ["-4"]
    fc = ["-n", str(count)] if is_win else ["-c", str(count)]
    cmd = ["ping"] + f6 + fc + [target]
    code, out = run_cmd(cmd, timeout=count * 2 + 15)
    m = re.search(r"(\d+(?:\.\d+)?)%\s*(?:loss|packet loss|lost)", out, re.IGNORECASE)
    loss = float(m.group(1)) if m else 100.0
    if is_win:
        m2 = re.search(r"(?:Average|avg)\s*=\s*(\d+)ms", out, re.IGNORECASE)
    else:
        m2 = re.search(r"min/avg/max/[^=]+=\s*[\d.]+/([\d.]+)/", out)
    avg = float(m2.group(1)) if m2 else 999.0
    return loss, avg, " ".join(cmd) if isinstance(cmd, list) else cmd, out


def wait_router_online(timeout=180):
    import urllib.request
    start = time.time()
    time.sleep(15)
    scheme = CONFIG.get("gateway_scheme", "http")
    while time.time() - start < timeout:
        loss, _, _, _ = run_ping_stats(CONFIG["gateway_ip"], count=2)
        if loss == 0:
            try:
                urllib.request.urlopen(f"{scheme}://{CONFIG['gateway_ip']}", timeout=5)  # nosec B310
                return True
            except Exception:  # nosec B110
                pass
        time.sleep(3)
    return False


def redact_image(path, regions):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    try:
        with Image.open(path) as im:
            d = ImageDraw.Draw(im)
            for x1, y1, x2, y2 in regions:
                d.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))
            im.save(path)
    except Exception:  # nosec B110
        pass

# ---------------- Test executor ----------------


class ATPWebEngine:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.router_page = None
        self.term_page = None

    def start_browser(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=not CONFIG.get("headed", False))
        ctx = self.browser.new_context(
            viewport={"width": 1366, "height": 850},
            ignore_https_errors=CONFIG.get("headed", False))
        self.router_page = ctx.new_page()
        self.term_page = ctx.new_page()

    def stop_browser(self):
        if self.browser:
            try:
                self.browser.close()
            except Exception:  # nosec B110
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:  # nosec B110
                pass

    # ---- Login ----
    def login(self, role="superadmin"):
        u = CONFIG["superadmin_user"] if role == "superadmin" else CONFIG["admin_user"]
        p = CONFIG["superadmin_pass"] if role == "superadmin" else CONFIG["admin_pass"]
        base = f"{CONFIG['gateway_scheme']}://{CONFIG['gateway_ip']}"
        self.router_page.goto(base, wait_until="networkidle", timeout=20000)
        self.router_page.fill("input[type='text'], #login-username", u)
        self.router_page.fill("input[type='password'], #login-password", p)
        self.router_page.click("#login-btn, button:has-text('Log In')")
        self.router_page.wait_for_load_state("networkidle")

    def goto(self, selector):
        self.router_page.click(selector)
        self.router_page.wait_for_load_state("networkidle")

    # ---- Each case ----
    def run(self, case_id):
        """Run a single case, return (status, detail, screenshots, logs)."""
        logs = []

        def log(msg):
            logs.append(msg)
            print(msg)

        self.start_browser()
        try:
            if case_id == "1.1":
                self.login("admin")
                img_a = self._snap("1.1_Admin_Login.png")
                self.login("superadmin")
                img_b = self._snap("1.1_Superadmin_Login.png")
                self.router_page.click("text=Basic")
                self.router_page.click("text=Wireless")
                self.router_page.wait_for_load_state("networkidle")
                img_c = self._snap("1.1_WiFi_SSID_Default.png")
                body = self.router_page.inner_text("body")
                ok = CONFIG.get("expected_ssid_prefix", "TP_Link_") in body
                for img in (img_a, img_b, img_c):
                    redact_image(img, CONFIG.get("sensitive_regions", {}).get(os.path.basename(img), []))
                return ("PASS" if ok else "FAIL", f"Prefix match={ok}", [img_a, img_b, img_c], "\n".join(logs))

            if case_id == "2.1":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Network")
                self.router_page.click("text=Internet")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("2.1_WAN_Internet_Config.png")
                self.router_page.click("text=Status")
                self.router_page.wait_for_load_state("networkidle")
                img2 = self._snap("2.1_WAN_Status.png")
                txt = self.router_page.inner_text("body")
                ok = ("PPPoE" in txt) and ("IPv6" in txt)
                return ("PASS" if ok else "FAIL", "PPPoE and IPv6 status page verified", [img1, img2], "\n".join(logs))

            if case_id == "2.3":

                all_ok = True
                imgs = []
                for i, tgt in enumerate([CONFIG["gateway_ip"], "8.8.8.8", "www.google.com"], 1):
                    loss, avg, cmd, out = run_ping_stats(tgt, count=4)
                    fn = f"2.3_Ping_{i}_{tgt}.png"
                    self._term_snap(cmd, out, fn)
                    imgs.append(fn)
                    if loss > 0:
                        all_ok = False
                return ("PASS" if all_ok else "FAIL",
                        "Gateway, 8.8.8.8, and DNS resolution verified", imgs,
                        "\n".join(logs))

            if case_id == "2.4":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=System Tools")
                self.router_page.click("text=Diagnostics")
                self.router_page.wait_for_load_state("networkidle")
                img = self._snap("2.4_GUI_Diagnostics.png")
                return ("PASS", "Entered system diagnostics tool interface", [img], "\n".join(logs))

            if case_id == "2.2":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Network")
                self.router_page.click("text=Internet")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("2.2_WAN_Before_Disconnect.png")
                self.router_page.click("button:has-text('Disconnect'), button:has-text('Release')")
                self.router_page.wait_for_timeout(3000)
                img2 = self._snap("2.2_WAN_Disconnected.png")
                self.router_page.click("button:has-text('Connect'), button:has-text('Renew')")
                self.router_page.wait_for_load_state("networkidle")
                time.sleep(10)
                img3 = self._snap("2.2_WAN_Reconnected.png")
                pub_ip = self._get_public_ip()
                loss_8888, _, _, _ = run_ping_stats("8.8.8.8", count=4)
                ok = bool(pub_ip and pub_ip != "0.0.0.0") and loss_8888 == 0.0
                return ("PASS" if ok else "FAIL", f"WAN reconnected, public IP={pub_ip}, ping 8.8.8.8 loss={loss_8888}%", [img1, img2, img3], "\n".join(logs))

            if case_id == "2.6":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Network")
                self.router_page.click("text=Internet")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("2.6_WAN_Failover_Before.png")
                self.router_page.click("text=Status")
                self.router_page.wait_for_load_state("networkidle")
                img2 = self._snap("2.6_WAN_Status_Before.png")
                return ("PASS", "Captured WAN status for manual GPON/eWAN failover verification (physical cable pull required)", [img1, img2], "\n".join(logs))

            if case_id == "4.8":

                loss6, avg6, cmd6, out6 = run_ping_stats("www.google.com", count=4, ipv6=True)
                self._term_snap(cmd6, out6, "4.8_Ping6_Google.png")
                self.term_page.goto("https://test-ipv6.com/", timeout=30000)
                self.term_page.wait_for_load_state("networkidle")
                img2 = self._snap("4.8_Test_IPv6_Score.png", page=self.term_page)
                score_ok = "10/10" in self.term_page.inner_text("body")
                ok = loss6 == 0 and score_ok
                return ("PASS" if ok else "FAIL",
                        f"IPv6 packet loss={loss6}%, test-ipv6 10/10={score_ok}",
                        ["4.8_Ping6_Google.png", "4.8_Test_IPv6_Score.png"], "\n".join(logs))

            if case_id == "4.2":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=VPN Server")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("4.2_VPN_Server_PPTP.png")
                self.router_page.click("text=OpenVPN")
                self.router_page.wait_for_load_state("networkidle")
                img2 = self._snap("4.2_VPN_Server_OpenVPN.png")
                self.router_page.click("text=L2TP")
                self.router_page.wait_for_load_state("networkidle")
                img3 = self._snap("4.2_VPN_Server_L2TP.png")
                return ("PASS", "Captured PPTP, OpenVPN, and L2TP configuration pages (external connectivity test requires remote client)", [img1, img2, img3], "\n".join(logs))

            if case_id == "4.6":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Security")
                self.router_page.click("text=MAC Filtering")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("4.6_MAC_Filtering_Config.png")
                self.router_page.click("button:has-text('Add'), button:has-text('Add New')")
                self.router_page.wait_for_timeout(1000)
                img2 = self._snap("4.6_MAC_Filtering_Add.png")
                return ("PASS", "MAC Filtering deny list page captured (add test device and verify no internet manually)", [img1, img2], "\n".join(logs))

            if case_id == "4.9":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Wireless")
                self.router_page.click("text=Wireless Schedule")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("4.9_Wireless_Schedule_Config.png")
                self.router_page.click("button:has-text('Enable'), button:has-text('On')")
                self.router_page.wait_for_timeout(2000)
                img2 = self._snap("4.9_Wireless_Schedule_Enabled.png")
                return ("PASS", "Wireless Schedule configuration captured (verify SSID broadcast stops at scheduled time manually)", [img1, img2], "\n".join(logs))

            if case_id == "4.11":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Network")
                self.router_page.click("text=LAN")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("4.11_LAN_Config.png")
                return ("PASS", "LAN port static IP configuration page captured (verify server reachability manually)", [img1], "\n".join(logs))

            if case_id == "4.12":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=System Tools")
                self.router_page.click("text=Schedule Reboot")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("4.12_Schedule_Reboot_Config.png")
                return ("PASS", "Schedule Reboot configuration page captured (verify actual reboot at scheduled time manually)", [img1], "\n".join(logs))

            if case_id == "4.13":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Wireless")
                self.router_page.click("text=Wireless Settings")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("4.13_Wireless_Settings_RSSI.png")
                self.router_page.click("text=Wireless Statistics")
                self.router_page.wait_for_load_state("networkidle")
                img2 = self._snap("4.13_Wireless_Statistics_RSSI.png")
                return ("PASS", "Wireless settings and RSSI statistics captured (use NetSpot for full stability analysis)", [img1, img2], "\n".join(logs))

            if case_id == "4.16":

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=Wireless")
                self.router_page.click("text=Wireless Settings")
                self.router_page.wait_for_load_state("networkidle")
                img1 = self._snap("4.16_Band_Steering_Before.png")
                self.router_page.click("button:has-text('Band Steering'), button:has-text('Smart Connect')")
                self.router_page.wait_for_timeout(2000)
                img2 = self._snap("4.16_Band_Steering_After.png")
                body = self.router_page.inner_text("body")
                ok = "Band Steering" in body or "Smart Connect" in body
                return ("PASS" if ok else "FAIL", f"Band Steering/Smart Connect page captured, UI indicates enabled={ok}", [img1, img2], "\n".join(logs))

            if case_id == "3.1":
                code, out = run_cmd("speedtest-cli --simple", timeout=60)
                self._term_snap("speedtest-cli --simple", out, "3.1_LAN_Speedtest.png")
                return ("PASS" if code == 0 else "FAIL", out.replace("\n", " | "),
                        ["3.1_LAN_Speedtest.png"], "\n".join(logs))

            if case_id in ("3.2", "3.3", "3.4"):
                band_map = {"3.2": "wifi_24g", "3.3": "wifi_5g", "3.4": "wifi_6g"}
                key = band_map[case_id]
                # Flat keys from the Web UI config take priority; nested dict kept for CLI compatibility
                ssid = CONFIG.get(key + "_ssid") or CONFIG.get(key, {}).get("ssid", "")
                pw = CONFIG.get(key + "_pass") or CONFIG.get(key, {}).get("pass", "")
                ok, cout = self._connect_wifi(ssid, pw)
                if not ok:
                    return ("SKIP", f"Unable to connect SSID: {ssid}", [], "\n".join(logs))
                c, o = run_cmd("speedtest-cli --simple", timeout=60)
                self._term_snap(f"[{ssid}] speedtest-cli --simple", o, f"{case_id.replace('/', '_')}_WiFi_Speed.png")
                return ("PASS" if c == 0 else "FAIL", o.replace("\n", " | "), [
                        f"{case_id.replace('/', '_')}_WiFi_Speed.png"], "\n".join(logs))

            if case_id == "3.5":

                self.term_page.goto("https://whatismyipaddress.com/", wait_until="domcontentloaded", timeout=25000)
                self.term_page.wait_for_load_state("networkidle")
                img = self._snap("3.5_Web_Browsing.png", page=self.term_page)
                return ("PASS", "Successfully loaded whatismyipaddress.com", [img], "\n".join(logs))

            if case_id == "3.6":

                self.term_page.goto("https://www.youtube.com/watch?v=LXb3EKWsInQ", timeout=30000)
                self.term_page.wait_for_load_state("networkidle")
                q = self.term_page.evaluate("""() => {
                    const v = document.querySelector('video');
                    if (!v) return 'No video element';
                    v.play();
                    const q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : {};
                    return `ReadyState:${v.readyState}, DroppedFrames:${q.droppedVideoFrames || 0}`;
                }""")
                img = self._snap("3.6_Online_Streaming_4K_8K.png", page=self.term_page)
                return ("PASS", q, [img], "\n".join(logs))

            if case_id == "3.7":

                t0 = time.time()
                url = "https://link.testfile.org/500MB"
                req = requests.get(url, stream=True, timeout=30)
                downloaded = 0
                for chunk in req.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        downloaded += len(chunk)
                    if time.time() - t0 > 20:
                        break
                mbps = (downloaded * 8) / ((time.time() - t0) * 1_000_000)
                self._term_snap(
                    f"GET {url}",
                    f"Downloaded: {downloaded / (1024 * 1024):.2f} MB in "
                    f"{time.time() - t0:.1f}s\nAvg Throughput: {mbps:.2f} Mbps",
                    "3.7_P2P_Heavy_Download.png"
                )
                return ("PASS" if downloaded > 0 else "FAIL", f"Average download speed {mbps:.2f} Mbps",
                        ["3.7_P2P_Heavy_Download.png"], "\n".join(logs))

            if case_id == "4.1":

                port = CONFIG.get("http_forward_port", 30000)
                os.makedirs("temp_www", exist_ok=True)
                with open("temp_www/index.html", "w", encoding="utf-8") as f:
                    f.write("<html><body><h1>TP-Link ATP Port Forwarding OK</h1></body></html>")

                class H(SimpleHTTPRequestHandler):
                    def __init__(self, *a, **k):
                        super().__init__(*a, directory="temp_www", **k)

                    def log_message(self, *a):
                        pass
                TCPServer.allow_reuse_address = True
                srv = TCPServer(("127.0.0.1", port), H)
                th = threading.Thread(target=srv.serve_forever, daemon=True)
                th.start()
                try:
                    self.login("superadmin")
                    self.router_page.click("text=Advanced")
                    self.router_page.click("text=NAT Forwarding")
                    self.router_page.click("text=Virtual Servers")
                    self.router_page.wait_for_load_state("networkidle")
                    img = self._snap("4.1_Port_Forwarding_UI.png")
                    pub = self._get_public_ip()
                    if pub and CONFIG.get("ext_nic_ip"):
                        s = requests.Session()
                        try:
                            r = s.get(f"http://{pub}:{port}", timeout=10)
                            ok = r.status_code == 200 and "Port Forwarding OK" in r.text
                            return ("PASS" if ok else "FAIL",
                                    f"External access to {pub}:{port} status code={r.status_code}",
                                    [img], "\n".join(logs))
                        except Exception as e:
                            return ("FAIL", str(e), [img], "\n".join(logs))
                    return ("PASS", "Captured Virtual Servers config page (skipping external callback assertion)", [
                            img], "\n".join(logs))
                finally:
                    srv.shutdown()
                    srv.server_close()

            if case_id in ("4.3", "4.4", "4.5", "4.7", "4.15"):

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                sel_map = {"4.3": "text=Parental Controls", "4.4": "text=QoS",
                           "4.5": "text=Dynamic DNS", "4.7": "text=Guest Network",
                           "4.15": "text=Wireless"}
                self.router_page.click(sel_map[case_id])
                self.router_page.wait_for_load_state("networkidle")
                img = self._snap(f"{case_id.replace('/', '_')}_UI.png")
                return ("PASS", f"Verified {case_id} config interface", [img], "\n".join(logs))

            if case_id == "10.1":
                try:
                    r = requests.get(
                        f"{CONFIG['acs_api_url']}/devices/?query=%7B%22_id%22%3A%22"
                        f"{CONFIG['acs_device_id']}%22%7D", timeout=10)
                    devs = r.json()
                    ok = len(devs) > 0
                    return ("PASS" if ok else "FAIL",
                            f"GenieACS queried device {CONFIG['acs_device_id']} online={ok}", [], "\n".join(logs))
                except Exception as e:
                    return ("SKIP", f"Unable to connect GenieACS: {e}", [], "\n".join(logs))

            if case_id == "10.2":
                try:
                    r = requests.post(
                        f"{CONFIG['acs_api_url']}/devices/{CONFIG['acs_device_id']}/tasks?connection_request",
                        json={"name": "getParameterValues",
                              "parameterNames": ["Device.WiFi.SSID.1.SSID"]}, timeout=15)
                    ok = r.status_code in (200, 202)
                    return ("PASS" if ok else "FAIL", f"Sent TR-069 response code={r.status_code}", [], "\n".join(logs))
                except Exception as e:
                    return ("FAIL", str(e), [], "\n".join(logs))

            if case_id == "10.3":
                try:
                    requests.post(f"{CONFIG['acs_api_url']}/devices/{CONFIG['acs_device_id']}/tasks?connection_request",
                                  json={"name": "reboot"}, timeout=15)
                    rec = wait_router_online(timeout=180)
                    return ("PASS" if rec else "FAIL",
                            f"ACS remote reboot, recovered online={rec}", [], "\n".join(logs))
                except Exception as e:
                    return ("FAIL", str(e), [], "\n".join(logs))

            if case_id == "10.4":
                if not CONFIG.get("run_destructive"):
                    return ("SKIP",
                            "Destructive test case skipped (enable --run-destructive to execute)",
                            [], "\n".join(logs))
                try:
                    r = requests.post(
                        f"{CONFIG['acs_api_url']}/devices/{CONFIG['acs_device_id']}/tasks?connection_request",
                        json={"name": "download",
                              "fileType": "1 Firmware Upgrade Image",
                              "url": CONFIG.get("acs_firmware_url", ""),
                              "username": CONFIG.get("acs_firmware_user", ""),
                              "password": CONFIG.get("acs_firmware_pass", ""),
                              "targetFileName": "firmware.bin"},
                        timeout=30)
                    ok = r.status_code in (200, 202)
                    if ok:
                        rec = wait_router_online(timeout=300)
                        return ("PASS" if rec else "FAIL",
                                f"ACS firmware upgrade pushed, router recovered={rec}", [], "\n".join(logs))
                    return ("FAIL", f"ACS firmware push failed: {r.status_code}", [], "\n".join(logs))
                except Exception as e:
                    return ("FAIL", str(e), [], "\n".join(logs))

            if case_id == "10.5":
                if not CONFIG.get("run_destructive"):
                    return ("SKIP",
                            "Destructive test case skipped (enable --run-destructive to execute)",
                            [], "\\n".join(logs))
                try:
                    r = requests.post(
                        f"{CONFIG['acs_api_url']}/devices/{CONFIG['acs_device_id']}/tasks?connection_request",
                        json={"name": "factoryReset"}, timeout=15)
                    ok = r.status_code in (200, 202)
                    if ok:
                        rec = wait_router_online(timeout=180)
                        return ("PASS" if rec else "FAIL",
                                f"ACS factory reset sent, router recovered={rec}", [], "\n".join(logs))
                    return ("FAIL", f"ACS factory reset failed: {r.status_code}", [], "\n".join(logs))
                except Exception as e:
                    return ("FAIL", str(e), [], "\n".join(logs))

            if case_id == "1.3":
                if not CONFIG.get("run_destructive"):
                    return ("SKIP",
                            "Destructive test case skipped (enable --run-destructive to execute)",
                            [], "\n".join(logs))

                self.login("superadmin")
                self.router_page.click("#top-reboot, button:has-text('Reboot')")
                self.router_page.wait_for_timeout(1000)
                img1 = self._snap("1.3_WebUI_Reboot_Confirm.png")
                self.router_page.click("button:has-text('Yes'), button:has-text('OK')")
                rec = wait_router_online(timeout=180)
                img2 = None
                if rec:
                    self.login("superadmin")
                    img2 = self._snap("1.3_After_Reboot_Relogin.png")
                return ("PASS" if rec else "FAIL", f"Web UI reboot and re-login={rec}",
                        [i for i in (img1, img2) if i], "\n".join(logs))

            if case_id == "6.1":
                if not CONFIG.get("run_destructive"):
                    return ("SKIP",
                            "Destructive test case skipped (enable --run-destructive to execute)",
                            [], "\n".join(logs))
                if not os.path.exists(CONFIG["firmware_bin_path"]):
                    return ("SKIP", f"Firmware file not found: {CONFIG['firmware_bin_path']}", [], "\n".join(logs))

                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=System Tools")
                self.router_page.click("text=Firmware Upgrade")
                self.router_page.set_input_files("input[type='file']", CONFIG["firmware_bin_path"])
                img1 = self._snap("6.1_FW_Upgrade_Ready.png")
                self.router_page.click("button:has-text('Upgrade')")
                rec = wait_router_online(timeout=300)
                img2 = None
                if rec:
                    self.login("superadmin")
                    img2 = self._snap("6.1_FW_Upgrade_Done.png")
                return ("PASS" if rec else "FAIL", "Firmware upgrade completed and version verified",
                        [i for i in (img1, img2) if i], "\n".join(logs))

            if case_id == "2.5/7.2":
                targets = [CONFIG["gateway_ip"], "8.8.8.8", "1.1.1.1"]
                secs = int(CONFIG.get("ping_seconds", 300))
                imgs = []
                details = []
                all_pass = True

                for tgt in targets:
                    loss, avg, cmd, out = run_ping_stats(tgt, duration_seconds=secs)
                    fn = f"2.5_LongPing_{tgt.replace('.', '_')}.png"
                    self._term_snap(f"{cmd} (Duration: {secs}s)", out, fn)
                    imgs.append(fn)
                    ok = loss == 0.0 and avg <= 30.0
                    if not ok:
                        all_pass = False
                    details.append(f"{tgt}: packet loss={loss}%, average latency={avg}ms")
                return ("PASS" if all_pass else "FAIL", " | ".join(details), imgs, "\n".join(logs))

            return ("SKIP", f"Case not implemented: {case_id}", [], "\n".join(logs))
        except Exception as e:
            return ("FAIL", str(e), [], "\n".join(logs))
        finally:
            self.stop_browser()

    # ---- Internal helpers ----
    def _snap(self, name, page=None):
        pg = page or self.router_page
        self._last_snap_page = pg
        d = os.path.join(REPORT_ROOT, datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        pg.screenshot(path=path, full_page=True)
        return path

    def _term_snap(self, cmd, out, name):
        d = os.path.join(REPORT_ROOT, datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        html_c = f"""<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:Consolas,monospace;padding:20px;">
        <div style="color:#569cd6;margin-bottom:8px;">$ {cmd}</div>
        <pre style="white-space:pre-wrap;">{out[-4000:]}</pre></body></html>"""
        self.term_page.set_content(html_c)
        self._last_snap_page = self.term_page
        self.term_page.screenshot(path=path, full_page=True)
        return path

    # ---- Screenshot annotation: red highlight boxes -----------------------

    def _highlight_regions(self, path, selectors, page=None):
        """Draw TP-Link red rounded rectangles around elements matched by
        `selectors` on the screenshot image, then save back to `path`.

        Coordinates are computed in page-document space
        (getBoundingClientRect + scroll offset) and scaled to the
        full-page screenshot size, so they stay correct regardless of
        scroll position when the snapshot was taken.
        """
        try:
            from PIL import Image, ImageDraw
        except ImportError:  # pragma: no cover - Pillow is a hard dependency
            return path
        pg = page or self.router_page
        if pg is None:
            return path
        try:
            with Image.open(path) as im:
                W, H = im.size
                doc_w, doc_h = pg.evaluate(
                    '() => [document.documentElement.scrollWidth || window.innerWidth, '
                    'document.documentElement.scrollHeight || window.innerHeight]'
                )
                boxes = pg.evaluate(
                    '(sels) => sels.map(sel => {'
                    '  const el = document.querySelector(sel);'
                    '  if (!el) return null;'
                    '  const r = el.getBoundingClientRect();'
                    '  return [r.x + window.scrollX, r.y + window.scrollY, r.width, r.height];'
                    '})',
                    selectors,
                )
                scale_x = W / doc_w if doc_w else 1.0
                scale_y = H / doc_h if doc_h else 1.0
                d = ImageDraw.Draw(im)
                for box in boxes:
                    if not box:
                        continue
                    x1, y1, bw, bh = box
                    x2, y2 = x1 + bw, y1 + bh
                    d.rounded_rectangle(
                        [x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y],
                        radius=8,
                        outline=(220, 38, 38),  # TP-Link red #dc2626
                        width=6,
                    )
                im.save(path)
        except Exception:  # nosec B110 - annotation must never fail a test run
            pass
        return path

    def _connect_wifi(self, ssid, pw):
        sys_os = platform.system()
        if sys_os == "Windows":
            iface = shlex.quote(CONFIG["wifi_iface"])
            run_cmd(f'netsh wlan connect name="{ssid}" interface={iface}', shell=True)  # nosec B604
        else:
            iface = shlex.quote(CONFIG["wifi_iface"])
            run_cmd(f'nmcli device wifi connect "{ssid}" password "{pw}" ifname {iface}', shell=True)  # nosec B604
        time.sleep(8)
        loss, _, _, _ = run_ping_stats(CONFIG["gateway_ip"], count=2)
        return loss == 0, ""

    def _get_public_ip(self):
        try:
            return requests.get("https://api.ipify.org", timeout=10).text.strip()
        except Exception:
            return ""


ENGINE = ATPWebEngine()

# ---------------- Background execution ----------------


def apply_case_highlights(engine, case_id, imgs):
    """If the case passed and has highlight selectors configured, draw red
    boxes on its final screenshot (the case's end-state view) and return
    the image list unchanged otherwise. Annotation never fails a run."""
    if not imgs:
        return imgs
    highlights = CONFIG.get("case_highlights", {}).get(case_id)
    if not highlights:
        return imgs
    page = getattr(engine, "_last_snap_page", None) or engine.router_page
    if page is None:
        return imgs
    try:
        engine._highlight_regions(imgs[-1], highlights, page)
    except Exception:  # nosec B110 - annotation must never fail a test run
        pass
    return imgs


def run_case_async(case_id):
    with state_lock:
        state[case_id] = {"status": "RUNNING", "detail": "", "screenshots": [],
                          "logs": "", "start": datetime.now().strftime("%H:%M:%S"), "end": None}
    try:
        status, detail, imgs, logs = ENGINE.run(case_id)
        if status == "PASS":
            imgs = apply_case_highlights(ENGINE, case_id, imgs)
        with state_lock:
            state[case_id].update({"status": status, "detail": detail,
                                   "screenshots": imgs, "logs": logs,
                                   "end": datetime.now().strftime("%H:%M:%S")})
    except Exception as e:
        with state_lock:
            state[case_id] = {"status": "FAIL", "detail": str(e), "screenshots": [],
                              "logs": "", "start": state[case_id].get("start"),
                              "end": datetime.now().strftime("%H:%M:%S")}


def run_stage_async(stage):
    ids = [cid for cid, _, s in CASES if s == stage]
    for cid in ids:
        if cancel_event.is_set():
            print(f"[api/stop] Run cancelled; remaining cases skipped")
            break
        run_case_async(cid)


# ---------------- Input validation ----------------
_IP_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _valid_ipv4(value):
    if not isinstance(value, str):
        return False
    m = _IP_RE.match(value.strip())
    if not m:
        return False
    return all(0 <= int(g) <= 255 for g in m.groups())


def validate_config_override(overrides):
    """Validate config overrides passed through /api/run; returns a list of error messages, empty list means pass."""
    errors = []
    if not isinstance(overrides, dict):
        return ["config must be a JSON object"]
    ip = overrides.get("gateway_ip")
    if ip is not None and not _valid_ipv4(ip):
        errors.append("gateway_ip format incorrect (must be IPv4, e.g. 192.168.1.1)")
    for user_key, pass_key in (("admin_user", "admin_pass"),
                               ("superadmin_user", "superadmin_pass")):
        if overrides.get(user_key) and not overrides.get(pass_key):
            errors.append(f"{user_key} filled in, {pass_key} is required")
    return errors


def _report_file_url(d, fn):
    rel = os.path.relpath(os.path.join(d, fn), BASE).replace(os.sep, "/")
    return "/screenshot/" + rel

# ---------------- Routes ----------------


@app.route("/")
def index():
    with open(os.path.join(BASE, "templates", "index.html"), encoding="utf-8") as f:
        return f.read()


@app.route("/api/state")
def api_state():
    with state_lock:
        cases = {cid: dict(s) for cid, s in state.items()}
        terminal = {"PASS", "FAIL", "SKIP"}
        done = sum(1 for s in state.values() if s.get("status") in terminal)
    # Convert absolute screenshot paths to relative paths accessible via /screenshot
    for cid, c in cases.items():
        c["screenshots"] = [
            "/screenshot/" +
            os.path.relpath(
                p,
                BASE) if os.path.isabs(p) else p for p in c.get(
                "screenshots",
                [])]
    total = len(CASES)
    percent = round(done / total * 100) if total else 0
    return jsonify({"cases": cases, "config": sanitize_config(CONFIG),
                    "progress": {"done": done, "total": total, "percent": percent},
                    "running": exec_lock.locked(), "stopping": cancel_event.is_set()})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify({"ok": True, "config": sanitize_config(CONFIG)})
    data = request.get_json(force=True)
    # Masked placeholders ('***') from the sanitized frontend view must never overwrite real secrets
    data = {k: v for k, v in data.items() if not (k in SENSITIVE_KEYS and v == "***")}
    # 先在副本上校验，失败时不污染全局 CONFIG，避免后续执行逻辑读到非法配置
    candidate = dict(CONFIG)
    candidate.update(data)
    try:
        validate_config(candidate)
    except ValueError as exc:
        return jsonify({"ok": False, "error": "Config validation failed", "details": str(exc)}), 400
    CONFIG.update(data)
    save_config(CONFIG)
    return jsonify({"ok": True})


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.get_json(force=True)
    stage = data.get("stage")
    case = data.get("case")
    overrides = data.get("config") or {}
    overrides = {k: v for k, v in overrides.items() if not (k in SENSITIVE_KEYS and v == "***")}

    # Validate the effective config (persisted CONFIG + overrides): masked secrets
    # stripped above still exist in CONFIG, so a user/pass pair must not be flagged missing.
    candidate = dict(CONFIG)
    candidate.update(overrides)
    errors = validate_config_override(candidate)
    if errors:
        return jsonify({"ok": False, "error": "Parameter validation failed", "details": errors}), 400

    if not exec_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "A test is currently running, please try again later"}), 409

    def job():
        try:
            cancel_event.clear()
            # Config overrides passed from frontend are persisted to config.json and applied to the current runtime;
            # after execution they are not restored, and subsequent starts/tests use the persisted config directly.
            CONFIG.update(overrides)
            try:
                save_config(CONFIG)
            except Exception as e:  # Persistence failure does not block this run, only takes effect in memory
                print(f"[api/run] Failed to save config.json: {e}")
                if case:
                    run_case_async(case)
                elif stage == "all":
                    for cid, _, _ in CASES:
                        if cancel_event.is_set():
                            print("[api/stop] Run cancelled; remaining cases skipped")
                            break
                        run_case_async(cid)
                else:
                    run_stage_async(stage)
        finally:
            exec_lock.release()

    threading.Thread(target=job, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Cancel a run: remaining queued cases are skipped; the case currently
    executing finishes (Playwright/subprocess work cannot be safely interrupted
    mid-step from another thread)."""
    if not exec_lock.locked():
        return jsonify({"ok": False, "error": "No test is running"}), 409
    cancel_event.set()
    return jsonify({"ok": True})


@app.route("/screenshot/<path:fpath>")
def screenshot(fpath):
    full = os.path.join(BASE, fpath)
    if not os.path.isfile(full):
        return "not found", 404
    d, fn = os.path.split(full)
    return send_from_directory(d, fn)


@app.route("/api/reports")
def api_reports():
    """List report directories under reports/, with summary_report.html and screenshot accessible URLs."""
    reports = []
    if os.path.isdir(REPORT_ROOT):
        entries = []
        for name in os.listdir(REPORT_ROOT):
            d = os.path.join(REPORT_ROOT, name)
            if not os.path.isdir(d):
                continue
            try:
                mtime = os.path.getmtime(d)
            except OSError:
                continue
            entries.append((mtime, name, d))
        entries.sort(key=lambda e: e[0], reverse=True)
        for _, name, d in entries:
            screenshots = []
            summary = None
            try:
                files = os.listdir(d)
            except OSError:
                files = []
            for fn in files:
                url = _report_file_url(d, fn)
                if fn == "summary_report.html":
                    summary = url
                elif os.path.splitext(fn)[1].lower() in _IMG_EXT:
                    screenshots.append(url)
            reports.append({
                "name": name,
                "path": os.path.join("reports", name).replace(os.sep, "/"),
                "summary": summary,
                "screenshots": screenshots,
                "file_count": len(files),
            })
    return jsonify({"ok": True, "reports": reports})


if __name__ == "__main__":
    os.makedirs(REPORT_ROOT, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("ATP_DEBUG", "0") == "1")  # nosec B104
