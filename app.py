"""Local browser interface. Run with python app.py."""
import json
import sys
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import requests
sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import main

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
JOBS = {}
LOCK = threading.Lock()


def search(job_id, city):
    try:
        result = main(city, interactive=False)
        state = {"status": "done", **result}
    except requests.RequestException:
        state = {"status": "error", "error": "Cannot connect to the search service. Check your internet connection and try again."}
    except (ValueError, SystemExit) as exc:
        state = {"status": "error", "error": str(exc)}
    except Exception:
        state = {"status": "error", "error": "The search could not finish. Check the configuration and output folder, then try again."}
    with LOCK:
        JOBS[job_id] = state


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, content_type="application/json"):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            html = (ROOT / "web/index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self.send(200, html.encode(), "text/html; charset=utf-8")
        if self.path.startswith("/api/jobs/"):
            with LOCK:
                job = JOBS.get(self.path.removeprefix("/api/jobs/"))
            return self.send(200 if job else 404, job or {"error": "Search not found"})
        if self.path.startswith("/download/"):
            name = unquote(self.path.removeprefix("/download/"))
            with LOCK:
                allowed = any(j.get("file") == name for j in JOBS.values())
            if allowed and Path(name).name == name:
                path = ROOT / "output" / name
                if path.is_file():
                    return self.send(200, path.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/api/search":
            return self.send(404, {"error": "Not found"})
        if self.headers.get("X-App-Token") != TOKEN:
            return self.send(403, {"error": "Refresh the page and try again."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError()
            body = json.loads(self.rfile.read(size))
            city = body.get("city", "")
            if not isinstance(city, str):
                raise ValueError()
            city = " ".join(city.split())
            if not 2 <= len(city) <= 80 or not all(c.isalpha() or c in " ,.-'" for c in city):
                raise ValueError()
        except (ValueError, AttributeError, UnicodeError):
            return self.send(400, {"error": "Enter a city name, for example Pune or Jaipur, Rajasthan."})
        with LOCK:
            if any(j["status"] == "running" for j in JOBS.values()):
                return self.send(409, {"error": "A search is already running. Please wait for it to finish."})
            job_id = secrets.token_urlsafe(18)
            JOBS[job_id] = {"status": "running"}
        threading.Thread(target=search, args=(job_id, city), daemon=True).start()
        self.send(202, {"id": job_id})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"PI GURBANI REALESTATE is running at {url}", flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
