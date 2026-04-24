"""
openclaw_jarvis_integration.py
══════════════════════════════
Paste this into your OpenClaw orchestrator (or import it).
Gives OpenClaw the ability to:
  - Report its own status to JARVIS HUD
  - Log every self-improvement action
  - Enable/disable JARVIS capabilities
  - Register newly discovered services
  - Request pip package installs
  - Read the full improvement map

Usage:
    from openclaw_jarvis_integration import JarvisReporter
    jr = JarvisReporter()           # auto-finds JARVIS port
    jr.heartbeat(model="qwen3:1.7b")  # call this every 60s
    jr.log("patch", "Updated retry logic in orchestrator")
    jr.enable_capability("web_search")
"""

import requests, socket, time, logging

JARVIS_PORTS = [7474, 7475, 7476, 7477, 7478, 7479, 7480]
JARVIS_TOKEN = "jarvis-openclaw-secret-2026"   # must match jarvis.cfg

log = logging.getLogger("openclaw.jarvis")

class JarvisReporter:
    def __init__(self):
        self.base_url = self._find_jarvis()
        self._start   = time.time()
        self._tasks   = 0
        self._edits   = 0
        if self.base_url:
            log.info(f"[JarvisReporter] Connected to JARVIS at {self.base_url}")
        else:
            log.warning("[JarvisReporter] JARVIS HUD not found — reporting disabled")

    def _find_jarvis(self):
        for port in JARVIS_PORTS:
            try:
                r = requests.get(f"http://127.0.0.1:{port}/api/sysinfo", timeout=1)
                if r.status_code == 200:
                    return f"http://127.0.0.1:{port}"
            except:
                continue
        return None

    def _post(self, path, payload):
        if not self.base_url:
            return False
        try:
            r = requests.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"X-JARVIS-TOKEN": JARVIS_TOKEN},
                timeout=3,
            )
            return r.status_code == 200
        except Exception as e:
            log.debug(f"[JarvisReporter] POST {path} failed: {e}")
            return False

    def heartbeat(self, model=None, health="nominal", tasks=None, edits=None):
        """Call every 60s to keep OpenClaw status live on HUD."""
        if tasks is not None: self._tasks = tasks
        if edits is not None: self._edits = edits
        return self._post("/api/openclaw/update", {
            "openclaw_status": {
                "model_active":   model,
                "health":         health,
                "tasks_complete": self._tasks,
                "self_edits":     self._edits,
                "uptime_seconds": int(time.time() - self._start),
                "version":        "3.0",
            }
        })

    def log(self, action, detail, category="improvement"):
        """Log a self-improvement action to JARVIS HUD."""
        self._edits += 1
        return self._post("/api/openclaw/update", {
            "log_entry": {
                "action":   action,
                "detail":   detail,
                "category": category,
            }
        })

    def task_complete(self, description):
        self._tasks += 1
        return self.log("task_complete", description, category="task")

    def enable_capability(self, capability):
        """Tell JARVIS to show a capability as active."""
        return self._post("/api/openclaw/update", {"enable_capability": capability})

    def disable_capability(self, capability):
        return self._post("/api/openclaw/update", {"disable_capability": capability})

    def register_service(self, name, port, http_url=None, ws_url=None, status="online"):
        """Register a newly discovered service in the JARVIS service map."""
        return self._post("/api/services/register", {
            "name": name, "port": port,
            "http_url": http_url or f"http://127.0.0.1:{port}",
            "ws_url":   ws_url,
            "status":   status,
        })

    def report_incident(self, service, description, severity="warning"):
        return self._post("/api/services/incident", {
            "service": service, "description": description, "severity": severity
        })

    def install_package(self, package_name):
        """Ask JARVIS to pip install a package (async, JARVIS does it)."""
        return self._post("/api/openclaw/install", {"package": package_name})

    def complete_goal(self, goal_description):
        return self._post("/api/openclaw/update", {"complete_goal": goal_description})

    def get_map(self):
        """Fetch the full improvement map (for OpenClaw to read directives)."""
        if not self.base_url:
            return {}
        try:
            r = requests.get(f"{self.base_url}/api/openclaw/map", timeout=3)
            return r.json()
        except:
            return {}

    def get_capabilities(self):
        m = self.get_map()
        return m.get("capabilities", {})

    def get_pending_actions(self):
        m = self.get_map()
        return m.get("pending_actions", [])


# ── Example orchestrator loop ─────────────────────────────────────────────────
if __name__ == "__main__":
    import time
    jr = JarvisReporter()

    # On startup: read the map to get directives
    m = jr.get_map()
    print("JARVIS directives:")
    for d in m.get("directives", []):
        print(f"  {d}")

    # Check pending actions from JARVIS
    for action in jr.get_pending_actions():
        print(f"  Pending: {action}")

    # Main loop
    tick = 0
    while True:
        tick += 1
        # Heartbeat every 60s
        if tick % 60 == 0:
            jr.heartbeat(model="qwen3:8b", health="nominal")

        # Example: log a self-improvement
        if tick == 5:
            jr.log("optimize", "Reduced Gemini retry interval from 10s to 5s")
            jr.task_complete("Tuned rate limit backoff")
            jr.enable_capability("web_search")

        time.sleep(1)
