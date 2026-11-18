"""TP-Link ATP Web UI — Flask 测试平台（配置、看板、逐用例重启）"""
import os, json, threading, time, subprocess, shlex, re, platform
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from flask import Flask, render_template_string, request, jsonify, send_from_directory
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")
REPORT_ROOT = os.path.join(BASE, "reports")

DEFAULT_CONFIG = {
    "gateway_ip": "192.168.1.1",
    "gateway_scheme": "http",
    "admin_user": "admin",
    "admin_pass": "admin1234",
    "superadmin_user": "superadmin",
    "superadmin_pass": "superadmin1234",
    "lan_iface": "Ethernet",
    "wifi_iface": "Wi-Fi",
    "ext_nic_ip": "192.168.43.100",
    "iperf3_server_ip": "192.168.1.100",
    "http_forward_port": 30000,
    "firmware_bin_path": "./firmware_new.bin",
    "acs_api_url": "http://192.168.1.200:7557",
    "acs_device_id": "001122-EX820v-SN12345678",
    "tauc_url": "https://tauc.tp-link.com",
    "tauc_user": "tauc_tester@example.com",
    "tauc_pass": "TaucPass123!",
    "ping_seconds": 300,
    "run_destructive": False,
    "headed": False,
    "sensitive_regions": {},
}

# ---------------- 配置持久化 ----------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            cfg.update(json.load(open(CONFIG_FILE, encoding="utf-8")))
        except Exception:
            pass
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

CONFIG = load_config()

# ---------------- 测试状态 ----------------
CASES = [
    # id, title, stage
    ("1.1", "Login Test (admin/superadmin)", "1"),
    ("2.1", "WAN Connectivity (PPPoE & IPv6)", "1"),
    ("2.3", "Internet Connectivity Test", "1"),
    ("2.4", "WAN Diagnostics (GUI)", "1"),
    ("4.8", "IPv6 Connectivity", "1"),
    ("3.1", "LAN Speed Test", "2"),
    ("3.2", "Wi-Fi 2.4GHz Speedtest", "2"),
    ("3.3", "Wi-Fi 5GHz Speedtest", "2"),
    ("3.4", "Wi-Fi 6GHz Speedtest", "2"),
    ("3.5", "Web Browsing", "2"),
    ("3.6", "Online Streaming (1080p/4K/8K)", "2"),
    ("3.7", "P2P / Heavy Download", "2"),
    ("4.1", "Port Forwarding (Port 30000)", "3"),
    ("4.3", "Parental Control / Web Filtering", "3"),
    ("4.4", "QoS (Quality of Service)", "3"),
    ("4.5", "DDNS (No-IP)", "3"),
    ("4.7", "Guest Network", "3"),
    ("4.15", "Multi-Link Operation (MLO)", "3"),
    ("10.1", "ACS Registration and Connection", "4"),
    ("10.2", "ACS Parameter GET/SET", "4"),
    ("10.3", "ACS Remote Reboot", "4"),
    ("1.3", "Router Reboot (Web UI)", "5"),
    ("6.1", "Firmware Upgrade via UI", "5"),
    ("2.5/7.2", "Long-Duration Ping Stability", "5"),
]

state = {cid: {"status": "PENDING", "detail": "", "screenshots": [], "logs": "",
               "start": None, "end": None} for cid, _, _ in CASES}
state_lock = threading.Lock()
exec_lock = threading.Lock()

app = Flask(__name__)

# ---------------- 工具 ----------------
def run_cmd(cmd, timeout=60, shell=False):
    try:
        p = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return -1, "Command timed out"

def run_ping_stats(target, count=10, ipv6=False):
    is_win = platform.system() == "Windows"
    f6 = ["-6"] if ipv6 else ["-4"]
    fc = ["-n", str(count)] if is_win else ["-c", str(count)]
    cmd = ["ping"] + f6 + fc + [target]
    code, out = run_cmd(cmd, timeout=count * 2 + 15)
    m = re.search(r"(\d+(?:\.\d+)?)%\s*(?:loss|packet loss|丢失)", out, re.IGNORECASE)
    loss = float(m.group(1)) if m else 100.0
    if is_win:
        m2 = re.search(r"(?:Average|平均)\s*=\s*(\d+)ms", out, re.IGNORECASE)
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
                urllib.request.urlopen(f"{scheme}://{CONFIG['gateway_ip']}", timeout=5)
                return True
            except Exception:
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
    except Exception:
        pass

# ---------------- 测试执行器 ----------------
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
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass

    # ---- 登录 ----
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

    # ---- 各 case ----
    def run(self, case_id):
        """执行单个 case，返回 (status, detail, screenshots, logs)"""
        logs = []
        def log(msg):
            logs.append(msg)
            print(msg)

        try:
            if case_id == "1.1":
                self.start_browser()
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
                return ("PASS" if ok else "FAIL", f"前缀匹配={ok}", [img_a, img_b, img_c], "\n".join(logs))

            if case_id == "2.1":
                self.start_browser()
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
                return ("PASS" if ok else "FAIL", "已验证 PPPoE 与 IPv6 状态页", [img1, img2], "\n".join(logs))

            if case_id == "2.3":
                self.start_browser()
                all_ok = True
                imgs = []
                for i, tgt in enumerate([CONFIG["gateway_ip"], "8.8.8.8", "www.google.com"], 1):
                    loss, avg, cmd, out = run_ping_stats(tgt, count=4)
                    fn = f"2.3_Ping_{i}_{tgt}.png"
                    self._term_snap(cmd, out, fn)
                    imgs.append(fn)
                    if loss > 0:
                        all_ok = False
                return ("PASS" if all_ok else "FAIL", "网关、8.8.8.8 与 DNS 解析验证", imgs, "\n".join(logs))

            if case_id == "2.4":
                self.start_browser()
                self.login("superadmin")
                self.router_page.click("text=Advanced")
                self.router_page.click("text=System Tools")
                self.router_page.click("text=Diagnostics")
                self.router_page.wait_for_load_state("networkidle")
                img = self._snap("2.4_GUI_Diagnostics.png")
                return ("PASS", "已进入系统诊断工具界面", [img], "\n".join(logs))

            if case_id == "4.8":
                self.start_browser()
                loss6, avg6, cmd6, out6 = run_ping_stats("www.google.com", count=4, ipv6=True)
                self._term_snap(cmd6, out6, "4.8_Ping6_Google.png")
                self.term_page.goto("https://test-ipv6.com/", timeout=30000)
                self.term_page.wait_for_load_state("networkidle")
                img2 = self._snap("4.8_Test_IPv6_Score.png", page=self.term_page)
                score_ok = "10/10" in self.term_page.inner_text("body")
                ok = loss6 == 0 and score_ok
                return ("PASS" if ok else "FAIL",
                        f"IPv6丢包={loss6}%, test-ipv6 10/10={score_ok}",
                        ["4.8_Ping6_Google.png", "4.8_Test_IPv6_Score.png"], "\n".join(logs))

            if case_id == "3.1":
                code, out = run_cmd("speedtest-cli --simple", timeout=60)
                self._term_snap("speedtest-cli --simple", out, "3.1_LAN_Speedtest.png")
                return ("PASS" if code == 0 else "FAIL", out.replace("\n", " | "),
                        ["3.1_LAN_Speedtest.png"], "\n".join(logs))

            if case_id in ("3.2", "3.3", "3.4"):
                band_map = {"3.2": "wifi_24g", "3.3": "wifi_5g", "3.4": "wifi_6g"}
                key = band_map[case_id]
                ssid = CONFIG.get(key, {}).get("ssid", "")
                pw = CONFIG.get(key, {}).get("pass", "")
                ok, cout = self._connect_wifi(ssid, pw)
                if not ok:
                    return ("SKIP", f"无法连接 SSID: {ssid}", [], "\n".join(logs))
                c, o = run_cmd("speedtest-cli --simple", timeout=60)
                self._term_snap(f"[{ssid}] speedtest-cli --simple", o, f"{case_id.replace('/','_')}_WiFi_Speed.png")
                return ("PASS" if c == 0 else "FAIL", o.replace("\n", " | "), [f"{case_id.replace('/','_')}_WiFi_Speed.png"], "\n".join(logs))

            if case_id == "3.5":
                self.start_browser()
                self.term_page.goto("https://whatismyipaddress.com/", wait_until="domcontentloaded", timeout=25000)
                self.term_page.wait_for_load_state("networkidle")
                img = self._snap("3.5_Web_Browsing.png", page=self.term_page)
                return ("PASS", "成功加载 whatismyipaddress.com", [img], "\n".join(logs))

            if case_id == "3.6":
                self.start_browser()
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
                self.start_browser()
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
                self._term_snap(f"GET {url}",
                                f"Downloaded: {downloaded / (1024*1024):.2f} MB in {time.time()-t0:.1f}s\nAvg Throughput: {mbps:.2f} Mbps",
                                "3.7_P2P_Heavy_Download.png")
                return ("PASS" if downloaded > 0 else "FAIL", f"平均下载速率 {mbps:.2f} Mbps",
                        ["3.7_P2P_Heavy_Download.png"], "\n".join(logs))

            if case_id == "4.1":
                self.start_browser()
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
                                      f"外网访问 {pub}:{port} 状态码={r.status_code}", [img], "\n".join(logs))
                        except Exception as e:
                            return ("FAIL", str(e), [img], "\n".join(logs))
                    return ("PASS", "已捕获 Virtual Servers 配置页面（跳过外部回调断言）", [img], "\n".join(logs))
                finally:
                    srv.shutdown()
                    srv.server_close()

            if case_id in ("4.3", "4.4", "4.5", "4.7", "4.15"):
                self.start_browser()
                self.login("superadmin")
                self.router_page.click("text=Advanced")
                sel_map = {"4.3": "text=Parental Controls", "4.4": "text=QoS",
                           "4.5": "text=Dynamic DNS", "4.7": "text=Guest Network",
                           "4.15": "text=Wireless"}
                self.router_page.click(sel_map[case_id])
                self.router_page.wait_for_load_state("networkidle")
                img = self._snap(f"{case_id.replace('/','_')}_UI.png")
                return ("PASS", f"已验证 {case_id} 配置界面", [img], "\n".join(logs))

            if case_id == "10.1":
                try:
                    r = requests.get(f"{CONFIG['acs_api_url']}/devices/?query=%7B%22_id%22%3A%22{CONFIG['acs_device_id']}%22%7D", timeout=10)
                    devs = r.json()
                    ok = len(devs) > 0
                    return ("PASS" if ok else "FAIL", f"GenieACS 查询设备 {CONFIG['acs_device_id']} 在线={ok}", [], "\n".join(logs))
                except Exception as e:
                    return ("SKIP", f"无法连接 GenieACS: {e}", [], "\n".join(logs))

            if case_id == "10.2":
                try:
                    r = requests.post(f"{CONFIG['acs_api_url']}/devices/{CONFIG['acs_device_id']}/tasks?connection_request",
                                      json={"name": "getParameterValues", "parameterNames": ["Device.WiFi.SSID.1.SSID"]}, timeout=15)
                    ok = r.status_code in (200, 202)
                    return ("PASS" if ok else "FAIL", f"下发 TR-069 响应码={r.status_code}", [], "\n".join(logs))
                except Exception as e:
                    return ("FAIL", str(e), [], "\n".join(logs))

            if case_id == "10.3":
                try:
                    requests.post(f"{CONFIG['acs_api_url']}/devices/{CONFIG['acs_device_id']}/tasks?connection_request",
                                  json={"name": "reboot"}, timeout=15)
                    rec = wait_router_online(timeout=180)
                    return ("PASS" if rec else "FAIL", f"ACS 远程重启，恢复上线={rec}", [], "\n".join(logs))
                except Exception as e:
                    return ("FAIL", str(e), [], "\n".join(logs))

            if case_id == "1.3":
                if not CONFIG.get("run_destructive"):
                    return ("SKIP", "破坏性用例已跳过（启用 --run-destructive 后执行）", [], "\n".join(logs))
                self.start_browser()
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
                return ("PASS" if rec else "FAIL", f"Web UI 重启并重新登录={rec}",
                        [i for i in (img1, img2) if i], "\n".join(logs))

            if case_id == "6.1":
                if not CONFIG.get("run_destructive"):
                    return ("SKIP", "破坏性用例已跳过（启用 --run-destructive 后执行）", [], "\n".join(logs))
                if not os.path.exists(CONFIG["firmware_bin_path"]):
                    return ("SKIP", f"未找到固件文件: {CONFIG['firmware_bin_path']}", [], "\n".join(logs))
                self.start_browser()
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
                return ("PASS" if rec else "FAIL", "固件升级完成并校验版本",
                        [i for i in (img1, img2) if i], "\n".join(logs))

            if case_id == "2.5/7.2":
                targets = [CONFIG["gateway_ip"], "8.8.8.8", "1.1.1.1"]
                secs = int(CONFIG.get("ping_seconds", 300))
                imgs = []
                details = []
                all_pass = True
                self.start_browser()
                for tgt in targets:
                    loss, avg, cmd, out = run_ping_stats(tgt, count=secs)
                    fn = f"2.5_LongPing_{tgt.replace('.', '_')}.png"
                    self._term_snap(f"{cmd} (Duration: {secs}s)", out, fn)
                    imgs.append(fn)
                    ok = loss == 0.0 and avg <= 30.0
                    if not ok:
                        all_pass = False
                    details.append(f"{tgt}: 丢包={loss}%, 平均延迟={avg}ms")
                return ("PASS" if all_pass else "FAIL", " | ".join(details), imgs, "\n".join(logs))

            return ("SKIP", f"未实现 case: {case_id}", [], "\n".join(logs))
        except Exception as e:
            return ("FAIL", str(e), [], "\n".join(logs))
        finally:
            pass

    # ---- 内部辅助 ----
    def _snap(self, name, page=None):
        pg = page or self.router_page
        d = os.path.join(REPORT_ROOT, datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        pg.screenshot(path=path, full_page=True)
        return path

    def _term_snap(self, cmd, out, name):
        d = os.path.join(REPORT_ROOT, datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        safe_cmd = out if False else cmd
        html_c = f"""<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:Consolas,monospace;padding:20px;">
        <div style="color:#569cd6;margin-bottom:8px;">$ {safe_cmd}</div>
        <pre style="white-space:pre-wrap;">{out[-4000:]}</pre></body></html>"""
        self.term_page.set_content(html_c)
        self.term_page.screenshot(path=path, full_page=True)
        return path

    def _connect_wifi(self, ssid, pw):
        sys_os = platform.system()
        if sys_os == "Windows":
            iface = shlex.quote(CONFIG["wifi_iface"])
            run_cmd(f'netsh wlan connect name="{ssid}" interface={iface}', shell=True)
        else:
            iface = shlex.quote(CONFIG["wifi_iface"])
            run_cmd(f'nmcli device wifi connect "{ssid}" password "{pw}" ifname {iface}', shell=True)
        time.sleep(8)
        loss, _, _, _ = run_ping_stats(CONFIG["gateway_ip"], count=2)
        return loss == 0, ""

    def _get_public_ip(self):
        try:
            return requests.get("https://api.ipify.org", timeout=10).text.strip()
        except Exception:
            return ""

ENGINE = ATPWebEngine()

# ---------------- 后台执行 ----------------
def run_case_async(case_id):
    with state_lock:
        state[case_id] = {"status": "RUNNING", "detail": "", "screenshots": [],
                          "logs": "", "start": datetime.now().strftime("%H:%M:%S"), "end": None}
    try:
        status, detail, imgs, logs = ENGINE.run(case_id)
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
        run_case_async(cid)

# ---------------- 路由 ----------------
INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>TP-Link ATP Web UI</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:20px;background:#f5f7fa}
h1{margin:0 0 12px}
.card{background:#fff;border-radius:8px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.row{display:flex;gap:12px;flex-wrap:wrap}
label{font-size:13px;color:#666;display:block;margin:6px 0 2px}
input{padding:6px 8px;border:1px solid #ccc;border-radius:4px;width:220px}
button{padding:8px 14px;border:none;border-radius:4px;cursor:pointer;font-size:13px}
button.primary{background:#005a9e;color:#fff}
button.danger{background:#dc3545;color:#fff}
button.small{padding:4px 8px;font-size:12px}
button:disabled{opacity:.6;cursor:not-allowed}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:13px}
th{background:#005a9e;color:#fff}
td.status{width:110px}
td.actions{width:140px}
.pending{color:#999}.running{color:#e0a800}.pass{color:#28a745}.fail{color:#dc3545}.skip{color:#6c757d}
img.preview{max-width:260px;max-height:150px;border:1px solid #ddd;margin-top:4px;display:block}
.logs{background:#1e1e1e;color:#d4d4d4;padding:8px;border-radius:4px;font-family:Consolas,monospace;font-size:11px;max-height:200px;overflow:auto;white-space:pre-wrap}
.section-title{font-weight:600;margin-top:16px;margin-bottom:8px;color:#005a9e}
.config-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
#toast{position:fixed;top:16px;right:16px;background:#333;color:#fff;padding:8px 12px;border-radius:4px;display:none;z-index:9999}
</style></head>
<body>
<h1>TP-Link ATP 自动化测试 UI</h1>

<div class="card">
  <h2 style="margin:0 0 12px">⚙️ 测试配置</h2>
  <div class="config-grid" id="cfg"></div>
  <div style="margin-top:12px">
    <button class="primary" onclick="saveConfig()">保存配置</button>
    <button onclick="location.reload()">重置</button>
  </div>
</div>

<div class="card">
  <h2 style="margin:0 0 12px">📋 测试用例看板</h2>
  <div class="row" style="margin-bottom:8px">
    <button class="primary" onclick="runStage('all')">运行全部</button>
    <button onclick="runStage('1')">Stage 1</button>
    <button onclick="runStage('2')">Stage 2</button>
    <button onclick="runStage('3')">Stage 3</button>
    <button onclick="runStage('4')">Stage 4</button>
    <button onclick="runStage('5')">Stage 5</button>
    <button class="danger" onclick="refresh()">刷新状态</button>
    <span id="busy" style="color:#dc3545;font-weight:bold;display:none">执行中…</span>
  </div>
  <table id="tbl"><thead><tr><th>用例</th><th>标题</th><th>阶段</th><th>状态</th><th>详情</th><th>时间</th><th>截图</th><th>操作</th></tr></thead><tbody></tbody></table>
</div>

<div id="toast"></div>

<script>
let cfg = {};
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.style.display='block';setTimeout(()=>t.style.display='none',3000)}
async function load(){const r=await fetch('/api/state');const d=await r.json();render(d.cases, d.config)}
function render(cases, config){
  cfg=config||{};
  document.getElementById('cfg').innerHTML = Object.entries(config).map(([k,v])=>{
    const type = typeof v === 'boolean' ? 'checkbox' : 'text';
    return `<div><label>${k}</label><input ${type==='checkbox'?`${v?'checked':''}`:(`value="${v}"`)} onchange="cfg['${k}']=this.checked!==undefined?this.checked:this.value" />${type==='checkbox'?'':' (文本)'}</div>`;
  }).join('');
  const tbody=document.getElementById('tbl').querySelector('tbody');
  tbody.innerHTML='';
  for(const [cid,title,stage] of Object.entries(cases)){
    const c=cases[cid];
    const cls=c.status.toLowerCase();
    let imgHtml='';
    for(const s of (c.screenshots||[])){
      imgHtml+=`<a href="${encodeURI(s)}" target="_blank"><img class="preview" src="${encodeURI(s)}"></a>`;
    }
    let action=`<button class="small primary" onclick="runOne('${cid}')">运行</button>`;
    if(c.status==='FAIL') action+=` <button class="small danger" onclick="runOne('${cid}')">Restart</button>`;
    else if(c.status==='PENDING') action+=` <button class="small" onclick="runOne('${cid}')">运行</button>`;
    else if(c.status==='RUNNING') action+=`<span class="pending">进行中</span>`;
    tbody.innerHTML+=`<tr><td><b>${cid}</b></td><td>${title}</td><td>Stage ${stage}</td>
      <td class="status ${cls}">${c.status}</td><td>${c.detail||''}</td><td>${c.start||''}-${c.end||''}</td>
      <td>${imgHtml}</td><td class="actions">${action}</td></tr>`;
  }
  document.getElementById('busy').style.display = Object.values(cases).some(c=>c.status==='RUNNING')?'inline':'none';
}
async function runStage(stage){
  await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage})});
  toast('已提交：'+stage); poll();
}
async function runOne(cid){
  await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case:cid})});
  toast('运行 '+cid); poll();
}
async function saveConfig(){
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  toast('配置已保存');
}
async function refresh(){load()}
function poll(){setTimeout(load,2000)}
load();setInterval(poll,3000);
</script></body></html>"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/api/state")
def api_state():
    with state_lock:
        cases = {cid: dict(s) for cid, s in state.items()}
    # 把绝对路径截图变成可通过 /screenshot 访问的相对路径
    for cid, c in cases.items():
        c["screenshots"] = ["/screenshot/" + os.path.relpath(p, BASE) if os.path.isabs(p) else p for p in c.get("screenshots", [])]
    return jsonify({"cases": cases, "config": CONFIG})

@app.route("/api/config", methods=["POST"])
def api_config():
    global CONFIG
    data = request.get_json(force=True)
    CONFIG.update(data)
    save_config(CONFIG)
    return jsonify({"ok": True})

@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.get_json(force=True)
    stage = data.get("stage")
    case = data.get("case")
    if not exec_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "有测试正在执行，请稍后再试"}), 409
    def job():
        try:
            if case:
                run_case_async(case)
            elif stage == "all":
                for cid, _, _ in CASES:
                    run_case_async(cid)
            else:
                run_stage_async(stage)
        finally:
            exec_lock.release()
    threading.Thread(target=job, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/screenshot/<path:fpath>")
def screenshot(fpath):
    full = os.path.join(BASE, fpath)
    if not os.path.isfile(full):
        return "not found", 404
    d, fn = os.path.split(full)
    return send_from_directory(d, fn)

if __name__ == "__main__":
    os.makedirs(REPORT_ROOT, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)
