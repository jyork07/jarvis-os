"""
J.A.R.V.I.S HUD v3 - Final Optimised Build
==========================================
Features:
  - Runtime dependency auto-install
  - Config file (jarvis.cfg) - no rebuild needed to change settings
  - Auto service discovery with port scanning + health checks
  - Smart WebSocket relay with fallback chain (OpenClaw → Jayyorkbot → Ollama direct)
  - OpenClaw self-improvement map (read/write REST API)
  - Auto-installs packages OpenClaw requests
  - System tray icon (stays alive if browser closes)
  - Watchdog: restarts crashed services if possible
  - Persistent chat history (SQLite)
  - Crash recovery loop
  - Graceful port conflict resolution
  - Docker container management API
  - Wake word via keyboard hotkey (Ctrl+Space)
  - Clean shutdown handler
"""

# ── 0. Bootstrap: install deps before any other import ───────────────────────
import sys, os, subprocess, importlib, configparser, socket, time, json
import threading, logging, datetime, atexit, signal, sqlite3, hashlib, tempfile, shutil

REQUIRED_PKGS = {
    "flask":          "flask>=3.0.0",
    "flask_sock":     "flask-sock>=0.7.0",
    "psutil":         "psutil>=5.9.0",
    "websocket":      "websocket-client>=1.8.0",
    "requests":       "requests>=2.31.0",
    "pystray":        "pystray>=0.19.0",
    "PIL":            "Pillow>=10.0.0",
    "keyboard":       "keyboard>=0.13.5",
    "flask_cors":     "flask-cors>=4.0.0",
    "numpy":          "numpy>=1.26.0",
    "faster_whisper": "faster-whisper>=1.1.0",
    "ctranslate2":    "ctranslate2>=4.4.0",
}

def _install(pkgs):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *pkgs, "--quiet", "--disable-pip-version-check"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

if not getattr(sys, "frozen", False):
    missing = []
    for mod, pkg in REQUIRED_PKGS.items():
        try: importlib.import_module(mod)
        except ImportError: missing.append(pkg)
    if missing:
        print(f"[JARVIS] Installing: {missing}")
        _install(missing)

# ── 1. Imports ────────────────────────────────────────────────────────────────
import psutil, requests
from flask import Flask, render_template, jsonify, request as freq, send_from_directory, send_file
from flask_sock import Sock
from flask_cors import CORS

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    from faster_whisper import WhisperModel
    HAS_LOCAL_WHISPER = True
except ImportError:
    WhisperModel = None
    HAS_LOCAL_WHISPER = False

# ── Obsidian Integration ─────────────────────────────────────────────────────────
try:
    from obsidian_integration import ObsidianBrain, get_obsidian_brain
    HAS_OBSIDIAN = True
    obsidian_brain = None
except ImportError:
    HAS_OBSIDIAN = False
    obsidian_brain = None

# ── 2. Paths ──────────────────────────────────────────────────────────────────
IS_FROZEN  = getattr(sys, "frozen", False)
BASE_DIR   = sys._MEIPASS if IS_FROZEN else os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TMPL_DIR   = os.path.join(BASE_DIR, "templates")

# Data lives next to exe (or script), survives rebuilds
EXE_DIR    = os.path.dirname(sys.executable) if IS_FROZEN else os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(EXE_DIR, "jarvis_data")
os.makedirs(DATA_DIR, exist_ok=True)

CFG_FILE         = os.path.join(EXE_DIR, "jarvis.cfg")
MAP_FILE         = os.path.join(DATA_DIR, "improvement_map.json")
SVC_CACHE_FILE   = os.path.join(DATA_DIR, "service_cache.json")
HISTORY_DB       = os.path.join(DATA_DIR, "history.db")
LOG_FILE         = os.path.join(DATA_DIR, "jarvis.log")
LOCAL_WHISPER_MODEL = None

# ── 3. Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("jarvis")

# ── 4. Config ─────────────────────────────────────────────────────────────────
cfg = configparser.ConfigParser()

DEFAULTS = """
[jarvis]
hud_port = 7474
open_browser = true
kiosk_mode = false
api_token = jarvis-openclaw-secret-2026
stats_interval = 2
discovery_interval = 30
tray_icon = true

[openclaw]
ports = 8000,8001,9000,7500

[jayyorkbot]
ports = 8080,7070,5050,3000

[ollama]
ports = 11434
default_model = qwen3:1.7b
fallback_models = qwen3:1.7b

[fish_tts]
ports = 7860,8765,9880

[whisper]
ports = 9000,8765,5001,6006

[docker]
ports = 2375,2376

[gemini_proxy]
ports = 4000,4001,5000

[obsidian]
path = C:\\Users\\jamie\\Documents\\JARVIS-Brain
api_url = http://127.0.0.1:27123
api_key =
"""

cfg.read_string(DEFAULTS)
if os.path.exists(CFG_FILE):
    cfg.read(CFG_FILE)
else:
    # Write default config next to exe so user can edit it
    with open(CFG_FILE, "w") as f:
        f.write(DEFAULTS.strip())
    log.info(f"Created default config: {CFG_FILE}")

def cfgget(section, key, fallback=None):
    try:    return cfg.get(section, key)
    except: return fallback

def cfgbool(section, key, fallback=False):
    try:    return cfg.getboolean(section, key)
    except: return fallback

def cfgports(section):
    raw = cfgget(section, "ports", "")
    return [int(p.strip()) for p in raw.split(",") if p.strip().isdigit()]

HUD_PORT   = int(cfgget("jarvis", "hud_port", "7474"))
API_TOKEN  = cfgget("jarvis", "api_token", "jarvis-openclaw-secret-2026")
STATS_INT  = int(cfgget("jarvis", "stats_interval", "2"))
DISC_INT   = int(cfgget("jarvis", "discovery_interval", "30"))
OLLAMA_MDL = cfgget("ollama", "default_model", "qwen3:1.7b")
OBSIDIAN_PATH = cfgget("obsidian", "path", os.environ.get("JARVIS_OBSIDIAN_PATH", "C:\\Users\\jamie\\Documents\\JARVIS-Brain"))
OBSIDIAN_API_URL = cfgget("obsidian", "api_url", os.environ.get("JARVIS_OBSIDIAN_API_URL", "http://127.0.0.1:27123"))
OBSIDIAN_API_KEY = cfgget("obsidian", "api_key", os.environ.get("JARVIS_OBSIDIAN_API_KEY", ""))
os.environ["JARVIS_OBSIDIAN_PATH"] = OBSIDIAN_PATH
os.environ["JARVIS_OBSIDIAN_API_URL"] = OBSIDIAN_API_URL
os.environ["JARVIS_OBSIDIAN_API_KEY"] = OBSIDIAN_API_KEY

if HAS_OBSIDIAN:
    try:
        obsidian_brain = ObsidianBrain(OBSIDIAN_PATH, OBSIDIAN_API_KEY, OBSIDIAN_API_URL)
    except Exception as e:
        log.warning(f"Obsidian integration init failed: {e}")
        obsidian_brain = get_obsidian_brain()

# ── 5. Graceful port resolution ───────────────────────────────────────────────
def find_free_port(preferred):
    for port in [preferred] + list(range(preferred+1, preferred+20)):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", port))
            s.close()
            return port
        except OSError:
            continue
    return preferred

HUD_PORT = find_free_port(HUD_PORT)
log.info(f"HUD port resolved: {HUD_PORT}")

# ── 6. Chat history (SQLite) ──────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(HISTORY_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            role      TEXT NOT NULL,
            content   TEXT NOT NULL,
            source    TEXT DEFAULT 'unknown'
        )
    """)
    conn.commit()
    conn.close()

def db_add(role, content, source="unknown"):
    try:
        conn = sqlite3.connect(HISTORY_DB)
        conn.execute("INSERT INTO history (ts, role, content, source) VALUES (?,?,?,?)",
                     (datetime.datetime.now().isoformat(), role, content, source))
        conn.commit()
        conn.close()
    except: pass
    
    # Auto-log important messages to Obsidian
    if HAS_OBSIDIAN and source == "JARVIS":
        try:
            # Log significant messages to Obsidian
            if len(content) > 50 and role in ["user", "assistant"]:
                # Create a session memory entry
                session_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                obsidian_brain.create_jarvis_memory(
                    content if role == "user" else "",
                    content if role == "assistant" else "",
                    session_id
                )
                log.info(f"Logged to Obsidian: {role} message")
        except Exception as e:
            log.warning(f"Failed to log to Obsidian: {e}")

def db_recent(n=100):
    try:
        conn = sqlite3.connect(HISTORY_DB)
        rows = conn.execute(
            "SELECT ts, role, content, source FROM history ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        return [{"ts":r[0],"role":r[1],"content":r[2],"source":r[3]} for r in reversed(rows)]
    except: return []

init_db()

# ── 7. Service discovery ──────────────────────────────────────────────────────
def get_openclaw_token():
    try:
        p = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(p):
            with open(p, "r") as f:
                d = json.load(f)
                return d.get("gateway", {}).get("auth", {}).get("token")
    except: pass
    return None

OC_TOKEN = get_openclaw_token()
OC_WS_PATH = f"/ws?token={OC_TOKEN}" if OC_TOKEN else None

SERVICES_DEF = [
    ("Hermes",        cfgports("hermes") or cfgports("openclaw"),    "/health",   OC_WS_PATH),
    ("Jayyorkbot",    cfgports("jayyorkbot"),  "/health",   "/ws"),
    ("Ollama",        cfgports("ollama"),      "/api/tags", None),
    ("Home Assistant", [8123],                 "/",         None),
    ("Fish TTS",      cfgports("fish_tts"),    "/",         None),
    ("Whisper STT",   cfgports("whisper"),     "/asr",      None),
    ("Docker API",    cfgports("docker"),      "/_ping",    None),
    ("Gemini Proxy",  cfgports("gemini_proxy"),"/health",   "/ws"),
]

discovered   = {}   # name -> dict
_disc_lock   = threading.Lock()
_active_back = {"name": None, "ws_url": None}  # currently connected WS backend

def port_open(host, port, timeout=0.4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except:
        return False


def _http_probe_candidates(base_url, health_path):
    candidates = []
    if health_path:
        candidates.append(f"{base_url}{health_path}")
    candidates.append(base_url)
    if health_path != "/api/tags":
        candidates.append(f"{base_url}/api/tags")
    if health_path != "/api/openclaw/map":
        candidates.append(f"{base_url}/api/openclaw/map")
    if health_path != "/api/sysinfo":
        candidates.append(f"{base_url}/api/sysinfo")
    seen = set()
    ordered = []
    for item in candidates:
        if item and item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def http_check(base_url, health_path="/health", timeout=1.5):
    last_error = None
    for probe_url in _http_probe_candidates(base_url, health_path):
        try:
            t0 = time.time()
            r = requests.get(probe_url, timeout=timeout, verify=False)
            return r.status_code < 500, round((time.time() - t0) * 1000, 1), probe_url
        except Exception as e:
            last_error = e
    if last_error:
        log.debug(f"HTTP probe failed for {base_url}: {last_error}")
    return False, 0, None


def ws_check(url, timeout=1.5):
    try:
        import websocket as wsc
        conn = wsc.create_connection(url, timeout=timeout)
        conn.close()
        return True
    except:
        return False

def discover_services():
    found = {}
    for name, ports, hpath, wpath in SERVICES_DEF:
        # Internal Whisper handling
        if name == "Whisper STT" and HAS_LOCAL_WHISPER:
            found[name] = {
                "port": None, "http_url": f"https://127.0.0.1:{HUD_PORT}/api/voice/transcribe", 
                "ws_url": None, "status": "online (internal)", "latency_ms": 0,
                "last_seen": datetime.datetime.now().isoformat(),
            }
            continue

        for port in ports:
            if port_open("127.0.0.1", port):
                http_url = f"http://127.0.0.1:{port}"
                ok, lat, probe_url = http_check(http_url, hpath)
                ws_url   = f"ws://127.0.0.1:{port}{wpath}" if wpath else None
                ws_ok    = ws_check(ws_url) if ws_url else False
                status   = "online" if ok else "port_open"
                if wpath and not ws_ok:
                    ws_url = None
                    if name in ("Hermes", "Jayyorkbot", "Gemini Proxy") and not ok:
                        status = "offline"
                found[name] = {
                    "port": port, "http_url": http_url, "ws_url": ws_url,
                    "status": status,
                    "latency_ms": lat,
                    "probe_url": probe_url,
                    "last_seen": datetime.datetime.now().isoformat(),
                }
                log.info(f"[DISC] {name} @ :{port} ({found[name]['status']} {lat}ms)")
                break
        else:
            prev = discovered.get(name, {})
            found[name] = {
                "port": None, "http_url": None, "ws_url": None,
                "status": "offline", "latency_ms": 0,
                "last_seen": prev.get("last_seen"),
            }

    with _disc_lock:
        discovered.update(found)

    # Update active backend
    for sname in ["Hermes", "Jayyorkbot", "Gemini Proxy"]:
        s = found.get(sname, {})
        if s.get("ws_url"):
            _active_back["name"]   = sname
            _active_back["ws_url"] = s["ws_url"]
            break
    else:
        ollama = found.get("Ollama", {})
        if ollama.get("http_url") and ollama.get("status") in ("online", "port_open"):
            _active_back["name"] = f"Ollama ({OLLAMA_MDL})"
            _active_back["ws_url"] = ollama.get("http_url")
        else:
            _active_back["name"] = None
            _active_back["ws_url"] = None

    try:
        with open(SVC_CACHE_FILE, "w") as f:
            json.dump(found, f, indent=2)
    except: pass

def discovery_loop():
    while True:
        try: discover_services()
        except Exception as e: log.error(f"Discovery error: {e}")
        time.sleep(DISC_INT)

# First scan before server starts
discover_services()
threading.Thread(target=discovery_loop, daemon=True).start()

# Prefer the real OpenClaw control gateway when present on the configured port.
hermes_svc = discovered.get("Hermes", {})
if hermes_svc.get("http_url"):
    log.info(f"[JARVIS] Hermes gateway detected at {hermes_svc['http_url']}")
else:
    log.info("[JARVIS] Hermes gateway not detected yet, using Ollama fallback")


def _gateway_models_url(base_url):
    return f"{base_url}/models"


def _ollama_generate_url(base_url):
    return f"{base_url}/api/generate"


def _clean_model_response_text(data):
    response_text = data.get("response", "") or ""
    think_text = data.get("thinking") or data.get("reasoning") or ""
    if think_text and response_text.startswith(think_text):
        cleaned = response_text[len(think_text):].lstrip()
        if cleaned:
            response_text = cleaned
    return response_text.strip()


def _synthesize_browser_safe_wav(text):
    text = (text or "").strip()
    if not text:
        raise RuntimeError("No text to synthesize")

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg not available for local TTS")

    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    out_path = tmp.name
    try:
        proc = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"flite=text='{escaped}':voice=slt",
                "-ar",
                "22050",
                "-ac",
                "1",
                out_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError(proc.stderr.decode(errors="ignore")[:400] or "ffmpeg flite failed")
        return out_path
    except Exception:
        if os.path.exists(out_path):
            try:
                os.unlink(out_path)
            except Exception:
                pass
        raise


def _get_gateway_control_payload():
    hermes_svc = discovered.get("Hermes", {})
    ollama_svc = discovered.get("Ollama", {})
    
    # If Ollama is not available, return None
    if not ollama_svc.get("http_url"):
        return None
    
    # Use direct Ollama mode (Hermes gateway not compatible with current API)
    return {
        "gateway_url": None,
        "gateway_models": [],
        "ollama_url": ollama_svc["http_url"],
    }

# ── 8. Improvement map ────────────────────────────────────────────────────────
DEFAULT_MAP = {
    "version": 1,
    "schema":  "jarvis-improvement-map-v1",
    "created": datetime.datetime.now().isoformat(),

    # What JARVIS can currently do — OpenClaw toggles these
    "capabilities": {
        "voice_input":     True,
        "voice_output":    True,
        "webcam":          True,
        "system_stats":    True,
        "process_kill":    False,
        "file_browser":    False,
        "code_execution":  False,
        "web_search":      False,
        "docker_control":  False,
        "screen_capture":  False,
        "email_notify":    False,
        "wake_word":       True,
    },

    # Instructions OpenClaw reads on startup
    "directives": [
        f"JARVIS HUD running at http://127.0.0.1:{HUD_PORT}",
        f"Read full map:      GET  http://127.0.0.1:{HUD_PORT}/api/openclaw/map",
        f"Post improvement:   POST http://127.0.0.1:{HUD_PORT}/api/openclaw/update",
        f"Patch capability:   PATCH http://127.0.0.1:{HUD_PORT}/api/openclaw/map",
        f"Register service:   POST http://127.0.0.1:{HUD_PORT}/api/services/register",
        f"Report incident:    POST http://127.0.0.1:{HUD_PORT}/api/services/incident",
        f"Install package:    POST http://127.0.0.1:{HUD_PORT}/api/openclaw/install",
        f"Chat history:       GET  http://127.0.0.1:{HUD_PORT}/api/history",
        f"Auth header:        X-JARVIS-TOKEN: {API_TOKEN}",
        "All POST/PATCH endpoints require X-JARVIS-TOKEN header",
        "Increment self_edits counter on every self-modification",
        "Log every improvement action to improvement_log array",
        "Check pending_actions on startup and execute them",
        "Use auto_install_queue to request pip packages",
        "Update openclaw_status.health every 60 seconds",
    ],

    "improvement_log":  [],   # rolling 500 entries
    "pending_actions":  [],   # OpenClaw writes, JARVIS processes
    "auto_install_queue": [],

    "openclaw_status": {
        "last_seen":       None,
        "model_active":    None,
        "tasks_complete":  0,
        "self_edits":      0,
        "health":          "unknown",
        "version":         None,
        "uptime_seconds":  0,
    },

    "system_goals": [
        "Maintain 100% service uptime across the stack",
        "Reduce average AI response latency below 500ms",
        "Auto-recover any crashed service within 60 seconds",
        "Expand JARVIS capabilities list over time",
        "Log all anomalies and report patterns weekly",
        "Self-update improvement_log with completed goals",
    ],
}

def load_map():
    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE) as f:
                data = json.load(f)
            # Merge new keys from default (non-destructive upgrade)
            for k, v in DEFAULT_MAP.items():
                if k not in data:
                    data[k] = v
            # Always refresh directives with current port
            data["directives"] = DEFAULT_MAP["directives"]
            return data
        except Exception as e:
            log.error(f"Map load error: {e}")
    m = DEFAULT_MAP.copy()
    save_map(m)
    return m

def save_map(data):
    with open(MAP_FILE, "w") as f:
        json.dump(data, f, indent=2)

improvement_map = load_map()

# ── 9. Auth helper ────────────────────────────────────────────────────────────
def auth_ok():
    token = freq.headers.get("X-JARVIS-TOKEN", "")
    return token == API_TOKEN

# ── 10. Flask app ─────────────────────────────────────────────────────────────
app  = Flask(__name__, static_folder=STATIC_DIR, template_folder=TMPL_DIR)
CORS(app)
sock = Sock(app)
app.config["SECRET_KEY"] = hashlib.sha256(API_TOKEN.encode()).hexdigest()

# ── UI ─────────────────────────────────────────────────────────────────────────
@app.route("/")
@app.route("/index.html")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route("/access")
@app.route("/access-config")
def access_config_page():
    resp = send_from_directory(app.static_folder, 'assets/access-config.html')
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.after_request
def add_no_cache_headers(response):
    path = (freq.path or "").lower()
    if path == "/" or path.endswith("index.html") or "/static/assets/" in path:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ── System stats ───────────────────────────────────────────────────────────────
@app.route("/api/sysinfo")
def sysinfo():
    cpu  = psutil.cpu_percent(interval=0.1)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net  = psutil.net_io_counters()
    boot = psutil.boot_time()
    secs = int(time.time() - boot)
    h, m = divmod(secs // 60, 60)
    d, h = divmod(h, 24)
    uptime = f"{d}d {h}h {m}m" if d else f"{h}h {m}m"

    temps = {}
    try:
        raw = psutil.sensors_temperatures()
        if raw:
            for name, entries in raw.items():
                if entries:
                    temps[name] = round(entries[0].current, 1)
    except: pass

    battery = None
    try:
        b = psutil.sensors_battery()
        if b:
            battery = {"pct": round(b.percent), "plugged": b.power_plugged}
    except: pass

    per_cpu = psutil.cpu_percent(percpu=True) or []

    return jsonify({
        "cpu": round(cpu, 1),
        "cpu_count": psutil.cpu_count(),
        "cpu_per_core": per_cpu,
        "mem_used": round(mem.used/1e9, 2),
        "mem_total": round(mem.total/1e9, 2),
        "mem_pct": mem.percent,
        "disk_used": round(disk.used/1e9, 1),
        "disk_total": round(disk.total/1e9, 1),
        "disk_pct": round(disk.percent, 1),
        "net_sent_mb": round(net.bytes_sent/1e6, 1),
        "net_recv_mb": round(net.bytes_recv/1e6, 1),
        "net_pkts_sent": net.packets_sent,
        "net_pkts_recv": net.packets_recv,
        "temps": temps,
        "battery": battery,
        "uptime": uptime,
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        "hostname": socket.gethostname(),
        "platform": sys.platform,
        "active_backend": _active_back.get("name"),
        "obsidian_enabled": HAS_OBSIDIAN,
        "obsidian_path": OBSIDIAN_PATH if HAS_OBSIDIAN else None,
        "services": discovered,
    })

@app.route("/api/processes")
def processes():
    procs = []
    for p in sorted(
        psutil.process_iter(["pid","name","cpu_percent","memory_percent","status"]),
        key=lambda x: x.info.get("cpu_percent") or 0, reverse=True
    )[:15]:
        try:
            procs.append({
                "pid":    p.info["pid"],
                "name":   p.info["name"],
                "cpu":    round(p.info.get("cpu_percent") or 0, 1),
                "mem":    round(p.info.get("memory_percent") or 0, 1),
                "status": p.info.get("status", ""),
            })
        except: pass
    return jsonify(procs)

@app.route("/api/process/kill/<int:pid>", methods=["POST"])
def kill_process(pid):
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    try:
        p = psutil.Process(pid)
        p.terminate()
        log.warning(f"Process killed: {pid} ({p.name()})")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

# ── Services ───────────────────────────────────────────────────────────────────
@app.route("/api/services")
def services():
    with _disc_lock:
        return jsonify(dict(discovered))

@app.route("/api/services/rescan", methods=["POST"])
def services_rescan():
    threading.Thread(target=discover_services, daemon=True).start()
    return jsonify({"ok": True, "message": "Rescan started"})

@app.route("/api/services/register", methods=["POST"])
def services_register():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    data = freq.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    with _disc_lock:
        discovered[name] = {
            "port":       data.get("port"),
            "http_url":   data.get("http_url"),
            "ws_url":     data.get("ws_url"),
            "status":     data.get("status", "registered"),
            "latency_ms": data.get("latency_ms", 0),
            "last_seen":  datetime.datetime.now().isoformat(),
        }
    log.info(f"Service registered: {name}")
    return jsonify({"ok": True})

@app.route("/api/services/incident", methods=["POST"])
def services_incident():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    data = freq.json or {}
    log.warning(f"Incident: {data}")
    m = load_map()
    m.setdefault("incident_log", []).append({
        "ts": datetime.datetime.now().isoformat(), **data
    })
    m["incident_log"] = m["incident_log"][-200:]
    save_map(m)
    return jsonify({"ok": True})

# ── Improvement map ────────────────────────────────────────────────────────────
@app.route("/api/openclaw/map", methods=["GET"])
def oc_map_get():
    m = load_map()
    with _disc_lock:
        m["services_live"] = dict(discovered)
    m["active_backend"] = _active_back
    m["hud_port"]       = HUD_PORT
    m["generated_at"]   = datetime.datetime.now().isoformat()
    return jsonify(m)

@app.route("/api/openclaw/update", methods=["POST"])
def oc_update():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    data = freq.json or {}
    m    = load_map()

    if "openclaw_status" in data:
        m["openclaw_status"].update(data["openclaw_status"])
        m["openclaw_status"]["last_seen"] = datetime.datetime.now().isoformat()

    if "log_entry" in data:
        entry = {"ts": datetime.datetime.now().isoformat(), **data["log_entry"]}
        m["improvement_log"].append(entry)
        m["improvement_log"] = m["improvement_log"][-500:]
        log.info(f"[OC-LOG] {entry.get('action','?')} — {entry.get('detail','')}")

    if "enable_capability" in data:
        m["capabilities"][data["enable_capability"]] = True
        log.info(f"Capability enabled: {data['enable_capability']}")

    if "disable_capability" in data:
        m["capabilities"][data["disable_capability"]] = False

    if "pending_actions" in data:
        m["pending_actions"].extend(data["pending_actions"])

    if "complete_goal" in data:
        m.setdefault("completed_goals", []).append({
            "goal": data["complete_goal"],
            "ts":   datetime.datetime.now().isoformat(),
        })

    m["version"] = m.get("version", 1) + 1
    save_map(m)
    return jsonify({"ok": True, "version": m["version"]})

@app.route("/api/openclaw/map", methods=["PATCH"])
def oc_map_patch():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    data = freq.json or {}
    m    = load_map()
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            m[k].update(v)
        else:
            m[k] = v
    m["version"] = m.get("version", 1) + 1
    save_map(m)
    return jsonify({"ok": True, "version": m["version"]})

@app.route("/api/openclaw/install", methods=["POST"])
def oc_install():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    pkg = (freq.json or {}).get("package")
    if not pkg:
        return jsonify({"error": "package required"}), 400
    log.info(f"Auto-installing package: {pkg}")
    def _do():
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            log.info(f"Installed: {pkg}")
        except Exception as e:
            log.error(f"Install failed {pkg}: {e}")
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"ok": True, "installing": pkg})

@app.route("/api/improvement_log")
def improvement_log():
    m = load_map()
    n = int(freq.args.get("n", 100))
    return jsonify(m.get("improvement_log", [])[-n:])

@app.route("/api/capabilities")
def capabilities():
    m = load_map()
    return jsonify(m.get("capabilities", {}))

# ── History ────────────────────────────────────────────────────────────────────
@app.route("/api/history")
def history():
    n = int(freq.args.get("n", 100))
    return jsonify(db_recent(n))

# ── Ollama ─────────────────────────────────────────────────────────────────────
@app.route("/api/ollama/models")
def ollama_models():
    svc = discovered.get("Ollama", {})
    if not svc.get("http_url"):
        return jsonify({"error": "offline", "models": []})
    try:
        r = requests.get(f"{svc['http_url']}/api/tags", timeout=3)
        return jsonify(r.json())
    except:
        return jsonify({"error": "unreachable", "models": []})

@app.route("/api/ollama/generate", methods=["POST"])
def ollama_generate():
    body = freq.get_json(silent=True) or {}
    prompt = body.get("prompt") or body.get("text") or ""
    body["stream"] = False

    control = _get_gateway_control_payload()
    if not control:
        return jsonify({"error": "Ollama unavailable"}), 503

    requested_model = (body.get("model") or "").strip()
    gateway_models = control.get("gateway_models") or []
    fallback_models = [m.strip() for m in str(cfgget("ollama", "fallback_models", OLLAMA_MDL)).split(",") if m.strip()]
    explicit_model_requested = bool(requested_model)
    primary_model = requested_model if explicit_model_requested else OLLAMA_MDL
    model_candidates = []
    ordered_candidates = [primary_model, *fallback_models]
    if explicit_model_requested:
        ordered_candidates.extend(gateway_models)
    for candidate in ordered_candidates:
        if candidate and candidate not in model_candidates:
            model_candidates.append(candidate)

    last_error = None
    for selected_model in model_candidates:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use subprocess to call ollama directly (bypasses API issues)
                import subprocess
                import json
                
                log.info(f"Attempting model: {selected_model} via CLI (attempt {attempt + 1}/{max_retries})")
                
                result = subprocess.run(
                    ["ollama", "run", selected_model, prompt],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=60
                )
                
                if result.returncode != 0:
                    raise RuntimeError(f"Ollama CLI failed: {result.stderr}")
                
                response_text = result.stdout.strip()
                
                if not response_text:
                    log.warning(f"Model {selected_model} returned empty response")
                    continue
                
                data = {
                    "response": response_text,
                    "model": selected_model,
                    "source": "local-ollama-cli",
                    "obsidian_enabled": HAS_OBSIDIAN,
                    "done": True
                }
                
                log.info(f"Successfully generated response with {selected_model}: {response_text[:100]}...")

                # Log to database
                if prompt:
                    db_add("user", prompt, source="jarvis-ui")
                if data.get("response"):
                    db_add("assistant", data.get("response", ""), source=data["source"])
                    
                    # Persist to Obsidian brain (main memory)
                    if HAS_OBSIDIAN and obsidian_brain and prompt:
                        try:
                            session_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                            obsidian_brain.create_jarvis_memory(prompt, data.get("response", ""), session_id)
                            log.info(f"Persisted JARVIS exchange to Obsidian brain: {session_id}")
                        except Exception as e:
                            log.warning(f"Failed to persist JARVIS exchange to Obsidian: {e}")

                return jsonify(data)
            except Exception as e:
                last_error = e
                log.warning(f"Model attempt failed ({selected_model}, attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)

    return jsonify({"error": str(last_error) if last_error else "No model candidates succeeded", "gateway_url": control.get("gateway_url"), "ollama_url": control.get("ollama_url"), "model_candidates": model_candidates}), 503


@app.route("/api/tts", methods=["POST"])
def api_tts():
    body = freq.get_json(silent=True) or {}
    text = (body.get("text") or body.get("response") or "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        wav_path = _synthesize_browser_safe_wav(text[:800])
        return send_file(
            wav_path,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="jarvis-voice.wav",
            max_age=0,
        )
    finally:
        pass

def _preload_whisper():
    global LOCAL_WHISPER_MODEL
    if HAS_LOCAL_WHISPER and WhisperModel is not None:
        try:
            model_name = os.environ.get("JARVIS_LOCAL_WHISPER_MODEL", "Systran/faster-whisper-tiny.en")
            log.info(f"[VOICE] Pre-loading Whisper model: {model_name}")
            LOCAL_WHISPER_MODEL = WhisperModel(model_name, device="cpu", compute_type="int8")
            log.info("[VOICE] Whisper model ready")
        except Exception as e:
            log.error(f"[VOICE] Pre-load failed: {e}")

threading.Thread(target=_preload_whisper, daemon=True).start()

def _transcribe_with_local_whisper(audio_bytes, filename, language="en"):
    global LOCAL_WHISPER_MODEL
    if not HAS_LOCAL_WHISPER or WhisperModel is None:
        raise RuntimeError("Local Whisper runtime is not installed")

    if LOCAL_WHISPER_MODEL is None:
        model_name = os.environ.get("JARVIS_LOCAL_WHISPER_MODEL", "Systran/faster-whisper-tiny.en")
        log.info(f"Loading local Whisper model: {model_name}")
        LOCAL_WHISPER_MODEL = WhisperModel(model_name, device="cpu", compute_type="int8")

    # Validate audio data before processing
    if not audio_bytes or len(audio_bytes) < 100:
        raise RuntimeError(f"Audio file too small or empty: {len(audio_bytes) if audio_bytes else 0} bytes")

    suffix = os.path.splitext(filename or "jarvis-recording.webm")[1] or ".webm"
    temp_path = None
    decoded_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name

        # Check if file was written correctly
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 100:
            raise RuntimeError(f"Temp file invalid after write: {os.path.getsize(temp_path) if os.path.exists(temp_path) else 0} bytes")

        transcribe_path = temp_path
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path and suffix.lower() in {".webm", ".mp4", ".m4a", ".ogg", ".oga"}:
            decoded_path = f"{temp_path}.wav"
            convert = subprocess.run(
                [ffmpeg_path, "-y", "-fflags", "+discardcorrupt", "-err_detect", "ignore_err", "-i", temp_path, "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", decoded_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if convert.returncode == 0 and os.path.exists(decoded_path) and os.path.getsize(decoded_path) > 44:
                transcribe_path = decoded_path
                log.info(f"Successfully converted {suffix} to wav: {os.path.getsize(decoded_path)} bytes")
            else:
                stderr_text = convert.stderr.decode(errors='ignore')[:600]
                log.warning(f"Primary ffmpeg decode failed: {stderr_text}")
                # Try alternative: use original file if it's valid
                if os.path.getsize(temp_path) > 1000:
                    log.info("Using original audio file directly for transcription")
                    transcribe_path = temp_path
                else:
                    raise RuntimeError(f"Audio file too small for transcription: {os.path.getsize(temp_path)} bytes")

        segments, info = LOCAL_WHISPER_MODEL.transcribe(transcribe_path, language=language or "en", vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments if segment.text and segment.text.strip()).strip()
        if not text:
            raise RuntimeError("Transcription produced no text")
        return text, info
    finally:
        for cleanup_path in [decoded_path, temp_path]:
            if cleanup_path and os.path.exists(cleanup_path):
                try:
                    os.unlink(cleanup_path)
                except Exception:
                    pass

@app.route("/api/voice/transcribe", methods=["POST"])
def voice_transcribe():
    audio = freq.files.get("audio")
    if not audio:
        return jsonify({"error": "No audio uploaded"}), 400

    audio_bytes = audio.read()
    if not audio_bytes:
        return jsonify({"error": "Uploaded audio was empty"}), 400

    filename = audio.filename or "jarvis-recording.webm"
    content_type = audio.mimetype or "application/octet-stream"
    language = (freq.form.get("language") or "en").strip()
    prompt = (freq.form.get("prompt") or "").strip()

    openai_api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    openai_base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    openai_error = None

    if _is_local_request() and openai_api_key:
        try:
            response = requests.post(
                f"{openai_base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_api_key}"},
                data={
                    "model": "whisper-1",
                    "response_format": "json",
                    **({"language": language} if language else {}),
                    **({"prompt": prompt} if prompt else {}),
                },
                files={"file": (filename, audio_bytes, content_type)},
                timeout=120,
            )
            payload = response.json() if response.content else {}
            if response.status_code < 400:
                transcript = (payload.get("text") or payload.get("transcript") or "").strip()
                return jsonify({"ok": True, "text": transcript, "provider": "openai-whisper"})
            openai_error = payload.get("error", {}).get("message") or payload.get("message") or "Transcription failed"
            log.warning(f"OpenAI transcription unavailable, falling back to local Whisper: {openai_error}")
        except Exception as e:
            openai_error = str(e)
            log.warning(f"OpenAI transcription error, falling back to local Whisper: {e}")

    try:
        transcript, info = _transcribe_with_local_whisper(audio_bytes, filename, language)
        return jsonify({
            "ok": True,
            "text": transcript,
            "provider": "local-faster-whisper",
            "language": getattr(info, "language", language),
            "duration": getattr(info, "duration", None),
            "fallback_from": openai_error,
        })
    except Exception as e:
        log.error(f"Voice transcription failed: {e}")
        return jsonify({
            "ok": False,
            "error": str(e),
            "provider": "local-faster-whisper",
            "fallback_from": openai_error,
        }), 503

# ── Docker ─────────────────────────────────────────────────────────────────────
@app.route("/api/docker/containers")
def docker_containers():
    svc = discovered.get("Docker API", {})
    if svc.get("http_url"):
        try:
            r = requests.get(f"{svc['http_url']}/containers/json?all=1", timeout=3)
            return jsonify(r.json())
        except: pass
    try:
        out = subprocess.check_output(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode()
        containers = [json.loads(l) for l in out.strip().splitlines() if l.strip()]
        return jsonify(containers)
    except:
        return jsonify({"error": "Docker unavailable", "containers": []})

@app.route("/api/docker/container/<cid>/<action>", methods=["POST"])
def docker_action(cid, action):
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    if action not in ("start", "stop", "restart"):
        return jsonify({"error": "invalid action"}), 400
    try:
        subprocess.check_call(["docker", action, cid], timeout=15,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ── Obsidian Memory Integration ───────────────────────────────────────────────────
@app.route("/api/obsidian/memory/create", methods=["POST"])
def obsidian_create_memory():
    """Create a new memory entry in Obsidian"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    
    data = freq.json or {}
    title = data.get("title", "Untitled Memory")
    content = data.get("content", "")
    tags = data.get("tags", [])
    source = data.get("source", "JARVIS")
    category = data.get("category", "general")
    
    try:
        file_path = obsidian_brain.create_memory_entry(title, content, tags, source, category)
        log.info(f"Created Obsidian memory: {file_path}")
        return jsonify({"ok": True, "path": file_path})
    except Exception as e:
        log.error(f"Failed to create Obsidian memory: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/memory/search")
def obsidian_search_memory():
    """Search memory entries in Obsidian"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    
    query = freq.args.get("q", "")
    limit = int(freq.args.get("limit", 10))
    
    try:
        results = obsidian_brain.search_memory(query, limit)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        log.error(f"Failed to search Obsidian memory: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/memory/get")
def obsidian_get_memory():
    """Get a specific memory entry from Obsidian"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    
    filename = freq.args.get("file", "")
    
    try:
        content = obsidian_brain.get_memory(filename)
        if content:
            return jsonify({"ok": True, "content": content})
        else:
            return jsonify({"ok": False, "error": "Memory not found"}), 404
    except Exception as e:
        log.error(f"Failed to get Obsidian memory: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/memory/recent")
def obsidian_recent_memory():
    """Get recent memory entries from Obsidian"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    
    limit = int(freq.args.get("limit", 10))
    
    try:
        results = obsidian_brain.get_recent_memories(limit)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        log.error(f"Failed to get recent Obsidian memory: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/agent/memory", methods=["POST"])
def obsidian_agent_memory():
    """Create memory entry for agent interaction"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    
    data = freq.json or {}
    agent_name = data.get("agent_name", "Unknown Agent")
    message = data.get("message", "")
    context = data.get("context", "")
    
    try:
        file_path = obsidian_brain.create_agent_memory(agent_name, message, context)
        log.info(f"Created agent memory: {file_path}")
        return jsonify({"ok": True, "path": file_path})
    except Exception as e:
        log.error(f"Failed to create agent memory: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/jarvis/memory", methods=["POST"])
def obsidian_jarvis_memory():
    """Create memory entry for JARVIS interaction"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    
    data = freq.json or {}
    user_message = data.get("user_message", "")
    jarvis_response = data.get("jarvis_response", "")
    session_id = data.get("session_id", "")
    
    try:
        file_path = obsidian_brain.create_jarvis_memory(user_message, jarvis_response, session_id)
        log.info(f"Created JARVIS memory: {file_path}")
        return jsonify({"ok": True, "path": file_path})
    except Exception as e:
        log.error(f"Failed to create JARVIS memory: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/crosslink", methods=["POST"])
def obsidian_crosslink():
    """Create cross-reference link between memory entries"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    
    data = freq.json or {}
    source_file = data.get("source_file", "")
    target_file = data.get("target_file", "")
    reference_type = data.get("reference_type", "related")
    
    try:
        result = obsidian_brain.create_cross_reference(source_file, target_file, reference_type)
        return jsonify({"ok": result})
    except Exception as e:
        log.error(f"Failed to create cross-reference: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/link-all", methods=["POST"])
def obsidian_link_all():
    """Build a vault-wide index and cross-link recent JARVIS notes"""
    if not HAS_OBSIDIAN:
        return jsonify({"error": "Obsidian integration not available"}), 503
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401

    try:
        result = obsidian_brain.link_all_files()
        return jsonify({"ok": True, **result})
    except Exception as e:
        log.error(f"Failed to link Obsidian files: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/obsidian/status")
def obsidian_status():
    """Check Obsidian integration status"""
    if not HAS_OBSIDIAN or not obsidian_brain:
        return jsonify({"ok": True, "enabled": False})
    return jsonify({"ok": True, **obsidian_brain.get_status()})

# ── Config hot-reload ──────────────────────────────────────────────────────────
def _config_to_dict(parser):
    data = {}
    for section in parser.sections():
        data[section] = {k: v for k, v in parser.items(section)}
    return data


def _load_cfg_parser():
    parser = configparser.ConfigParser()
    parser.read(CFG_FILE)
    return parser


def _is_local_request():
    remote_addr = (freq.remote_addr or "").strip()
    return remote_addr in {"127.0.0.1", "::1"}


def _requests_verify_flag():
    verify_raw = str(os.environ.get("JARVIS_SKIP_TLS_VERIFY", "0")).strip().lower()
    return verify_raw not in {"1", "true", "yes", "on"}


def _parse_ports_csv(value):
    ports = []
    seen = set()
    for chunk in str(value or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            port = int(chunk)
        except ValueError:
            raise ValueError(f"Invalid port '{chunk}'")
        if port < 1 or port > 65535:
            raise ValueError(f"Port out of range: {port}")
        if port not in seen:
            ports.append(port)
            seen.add(port)
    return ports


def _validate_config_payload(payload):
    errors = []
    normalized = {}

    jarvis = payload.get("jarvis", {})
    hud_port_raw = jarvis.get("hud_port", "7474")
    try:
        hud_port = int(str(hud_port_raw).strip())
        if hud_port < 1 or hud_port > 65535:
            raise ValueError
    except Exception:
        errors.append("jarvis.hud_port must be a valid port between 1 and 65535")
        hud_port = 7474

    openclaw = payload.get("openclaw", {})
    try:
        openclaw_ports = _parse_ports_csv(openclaw.get("ports", "18789,8000,8001,9000,7500"))
    except ValueError as e:
        errors.append(f"openclaw.ports: {e}")
        openclaw_ports = [18789, 8000, 8001, 9000, 7500]

    ollama = payload.get("ollama", {})
    try:
        ollama_ports = _parse_ports_csv(ollama.get("ports", "11434"))
    except ValueError as e:
        errors.append(f"ollama.ports: {e}")
        ollama_ports = [11434]

    obsidian = payload.get("obsidian", {})
    obsidian_path = str(obsidian.get("path", OBSIDIAN_PATH)).strip()
    obsidian_api_url = str(obsidian.get("api_url", OBSIDIAN_API_URL)).strip() or OBSIDIAN_API_URL


    obsidian_api_key = str(obsidian.get("api_key", OBSIDIAN_API_KEY)).strip()
    if not obsidian_path or not os.path.isdir(obsidian_path):
        errors.append("obsidian.path must point to an existing directory")

    normalized["jarvis"] = {
        "hud_port": str(hud_port),
        "open_browser": str(jarvis.get("open_browser", "true")).lower(),
        "kiosk_mode": str(jarvis.get("kiosk_mode", "false")).lower(),
        "api_token": str(jarvis.get("api_token", API_TOKEN)).strip() or API_TOKEN,
        "stats_interval": str(jarvis.get("stats_interval", "2")).strip() or "2",
        "discovery_interval": str(jarvis.get("discovery_interval", "15")).strip() or "15",
        "tray_icon": str(jarvis.get("tray_icon", "true")).lower(),
    }
    normalized["openclaw"] = {"ports": ",".join(map(str, openclaw_ports))}
    normalized["jayyorkbot"] = {"ports": str(payload.get("jayyorkbot", {}).get("ports", "8080,7070,5050,3000"))}
    normalized["ollama"] = {
        "ports": ",".join(map(str, ollama_ports)),
        "default_model": str(ollama.get("default_model", "qwen3:1.7b")).strip() or "qwen3:1.7b",
        "fallback_models": str(ollama.get("fallback_models", "qwen3:1.7b,qwen3:8b,qwen:7b")).strip() or "qwen3:1.7b,qwen3:8b,qwen:7b",
    }
    normalized["fish_tts"] = {"ports": str(payload.get("fish_tts", {}).get("ports", "7860,8765,9880"))}
    normalized["whisper"] = {"ports": str(payload.get("whisper", {}).get("ports", "9000,8765,5001,6006"))}
    normalized["docker"] = {"ports": str(payload.get("docker", {}).get("ports", "2375,2376"))}
    normalized["gemini_proxy"] = {"ports": str(payload.get("gemini_proxy", {}).get("ports", "4000,4001,5000"))}
    normalized["obsidian"] = {
        "path": obsidian_path,
        "api_url": obsidian_api_url,
        "api_key": obsidian_api_key,
    }
    return errors, normalized


def _write_cfg_from_dict(data):
    parser = configparser.ConfigParser()
    for section, values in data.items():
        parser[section] = {k: str(v) for k, v in values.items()}
    with open(CFG_FILE, "w") as f:
        parser.write(f)

@app.route("/api/config", methods=["GET"])
def get_config():
    if not os.path.exists(CFG_FILE):
        return "", 404
    parser = _load_cfg_parser()
    return jsonify({"ok": True, "path": CFG_FILE, "config": _config_to_dict(parser)})

@app.route("/api/config/validate", methods=["POST"])
def validate_config():
    payload = freq.get_json(silent=True) or {}
    errors, normalized = _validate_config_payload(payload)
    return jsonify({"ok": len(errors) == 0, "errors": errors, "normalized": normalized})

@app.route("/api/config", methods=["POST"])
def set_config():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    payload = freq.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_json"}), 400
    errors, normalized = _validate_config_payload(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    _write_cfg_from_dict(normalized)
    return jsonify({"ok": True, "note": "Config saved. Restart JARVIS for all changes to take effect.", "path": CFG_FILE, "config": normalized})

# ── Watchdog ───────────────────────────────────────────────────────────────────
WATCHDOG_CMDS = {
    "Ollama": ["ollama", "serve"],
}

def watchdog_loop():
    """Attempt to restart known services that have a launch command."""
    time.sleep(60)
    while True:
        for name, cmd in WATCHDOG_CMDS.items():
            svc = discovered.get(name, {})
            if svc.get("status") == "offline":
                log.warning(f"[WATCHDOG] {name} offline — attempting restart")
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    log.info(f"[WATCHDOG] Restarted {name}")
                except FileNotFoundError:
                    pass
        time.sleep(60)

threading.Thread(target=watchdog_loop, daemon=True).start()

# ── WebSocket relay ────────────────────────────────────────────────────────────
@sock.route("/ws")
def ws_relay(ws):
    import websocket as wsc

    def connect_backend():
        for sname in ["Hermes", "Jayyorkbot", "Gemini Proxy"]:
            s = discovered.get(sname, {})
            if s.get("ws_url"):
                try:
                    conn = wsc.create_connection(s["ws_url"], timeout=3)
                    log.info(f"WS → {sname}")
                    return conn, sname
                except:
                    pass
        ollama = discovered.get("Ollama", {})
        if ollama.get("http_url"):
            return None, f"ollama-direct:{OLLAMA_MDL}"
        return None, None

    backend, bname = connect_backend()

    def fwd():
        if not backend: return
        try:
            while True:
                ws.send(backend.recv())
        except: pass

    if backend:
        threading.Thread(target=fwd, daemon=True).start()

    try:
        while True:
            raw = ws.receive()
            if raw is None: break

            try:
                payload = json.loads(raw) if raw.strip().startswith("{") else {"text": raw}
            except:
                payload = {"text": raw}

            text = payload.get("text", raw)
            db_add("user", text, source=bname or "local")

            if backend:
                try:
                    backend.send(raw)
                    continue
                except:
                    log.warning("Backend WS dropped, reconnecting")
                    backend, bname = connect_backend()
                    if backend:
                        threading.Thread(target=fwd, daemon=True).start()
                        backend.send(raw)
                        continue

            # Fallback: Ollama direct
            svc = discovered.get("Ollama", {})
            if svc.get("http_url"):
                try:
                    r = requests.post(
                        f"{svc['http_url']}/api/generate",
                        json={"model": OLLAMA_MDL, "prompt": text, "stream": False},
                        timeout=45
                    )
                    reply = r.json().get("response", "[No response from Ollama]")
                    db_add("assistant", reply, source="ollama-direct")
                    ws.send(json.dumps({
                        "type": "response", "text": reply,
                        "source": "ollama-direct",
                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    }))
                    continue
                except Exception as e:
                    log.error(f"Ollama direct fail: {e}")

            # Last resort
            msg = "[JARVIS] All AI backends offline. Check Hermes and Ollama."
            db_add("system", msg, source="jarvis-local")
            ws.send(json.dumps({
                "type": "response", "text": msg,
                "source": "jarvis-local",
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            }))

    except Exception as e:
        log.debug(f"WS client disconnected: {e}")
    finally:
        if False and backend:
            try: backend.close()
            except: pass

# ── Tray icon ─────────────────────────────────────────────────────────────────
def create_tray():
    if not HAS_TRAY or not cfgbool("jarvis", "tray_icon", True):
        return

    def make_icon():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, 60, 60], outline=(0, 212, 255), width=3)
        d.ellipse([16, 16, 48, 48], fill=(0, 212, 255, 200))
        return img

    def open_hud(icon, item):
        import webbrowser
        webbrowser.open(f"http://localhost:{HUD_PORT}")

    def quit_app(icon, item):
        icon.stop()
        os.kill(os.getpid(), signal.SIGTERM)

    icon = pystray.Icon(
        "JARVIS",
        make_icon(),
        "J.A.R.V.I.S",
        menu=pystray.Menu(
            pystray.MenuItem("Open HUD", open_hud, default=True),
            pystray.MenuItem("Quit", quit_app),
        )
    )
    threading.Thread(target=icon.run, daemon=True).start()
    log.info("Tray icon active")

# ── Hotkey ─────────────────────────────────────────────────────────────────────
_hotkey_ws_clients = []

def setup_hotkey():
    if not HAS_KEYBOARD:
        return
    def trigger():
        log.info("Hotkey: Ctrl+Space — wake word triggered")
        # Notify all connected WS clients
        msg = json.dumps({"type": "hotkey", "action": "wake", "timestamp": datetime.datetime.now().strftime("%H:%M:%S")})
        for cb in list(_hotkey_ws_clients):
            try: cb(msg)
            except: pass
    try:
        keyboard.add_hotkey("ctrl+space", trigger)
        log.info("Hotkey registered: Ctrl+Space")
    except Exception as e:
        log.warning(f"Hotkey failed: {e}")

# ── Launch ─────────────────────────────────────────────────────────────────────
SSL_CERT_PATH = os.path.join(DATA_DIR, "certs", "home-1.tail79f127.ts.net.crt")
SSL_KEY_PATH = os.path.join(DATA_DIR, "certs", "home-1.tail79f127.ts.net.key")


def _enable_tls():
    mode = str(os.environ.get("JARVIS_ENABLE_TLS", "0")).strip().lower()
    return mode in {"1", "true", "yes", "on"}


def open_browser_delayed():
    time.sleep(1.8)
    url = f"http://localhost:{HUD_PORT}"
    try:
        if cfgbool("jarvis", "kiosk_mode", False):
            candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
            for c in candidates:
                if os.path.exists(c):
                    subprocess.Popen([c, f"--app={url}", "--start-fullscreen",
                                      "--disable-infobars", "--no-first-run",
                                      "--disable-extensions"])
                    return
        import webbrowser
        webbrowser.open(url)
    except: pass

def cleanup(*_):
    log.info("JARVIS shutting down")
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT,  cleanup)
atexit.register(lambda: log.info("JARVIS exit"))

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("J.A.R.V.I.S HUD v3 starting")
    log.info(f"  HUD:      http://localhost:{HUD_PORT}")
    log.info(f"  Data:     {DATA_DIR}")
    log.info(f"  Config:   {CFG_FILE}")
    log.info(f"  Map:      {MAP_FILE}")
    log.info(f"  DB:       {HISTORY_DB}")
    log.info("=" * 60)

    create_tray()
    setup_hotkey()

    if cfgbool("jarvis", "open_browser", True):
        threading.Thread(target=open_browser_delayed, daemon=True).start()

    # TLS can be enabled explicitly for remote/mobile access, but plain HTTP stays the default
    # because several local clients and health checks expect it.
    ssl_context = None
    if _enable_tls() and os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
        ssl_context = (SSL_CERT_PATH, SSL_KEY_PATH)
        log.info(f"SSL active: {SSL_CERT_PATH}")
    elif _enable_tls():
        log.warning("JARVIS_ENABLE_TLS requested but cert/key files are missing, starting without TLS")

    app.run(host="0.0.0.0", port=HUD_PORT, debug=False, threaded=True, use_reloader=False, ssl_context=ssl_context)



