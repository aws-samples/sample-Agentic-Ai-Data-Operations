"""Serve the UI and control-plane API together for local development."""

from __future__ import annotations

import argparse
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .control_plane import ControlPlaneService, handler


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"


class Handler(BaseHTTPRequestHandler):
    service = ControlPlaneService()

    def _event(self, body: bytes = b"") -> dict:
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        return {
            "httpMethod": self.command,
            "rawPath": self.path,
            "queryStringParameters": {
                key: values[-1] for key, values in parse_qs(query).items() if values
            },
            "headers": {key: value for key, value in self.headers.items()},
            "body": body.decode("utf-8") if body else None,
        }

    def _send_api(self, response: dict) -> None:
        payload = response.get("body", "").encode("utf-8")
        self.send_response(response["statusCode"])
        for key, value in response.get("headers", {}).items():
            self.send_header(key, value)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _serve_ui(self) -> None:
        requested = self.path.split("?", 1)[0].lstrip("/") or "index.html"
        candidate = (UI_ROOT / requested).resolve()
        if UI_ROOT not in candidate.parents and candidate != UI_ROOT:
            self.send_error(404)
            return
        if not candidate.exists() or not candidate.is_file():
            candidate = UI_ROOT / "index.html"
        payload = candidate.read_bytes()
        self.send_response(200)
        self.send_header("content-type", mimetypes.guess_type(str(candidate))[0] or "text/plain")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self._send_api(handler(self._event(), service=self.service))

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._send_api(handler(self._event(), service=self.service))
        else:
            self._serve_ui()

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        self._send_api(handler(self._event(body), service=self.service))

    def log_message(self, format: str, *args: object) -> None:
        if os.getenv("ADOP_API_ACCESS_LOG", "1") == "1":
            super().log_message(format, *args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    os.environ.setdefault("ADOP_LOCAL_ALLOWED_ORIGINS", f"http://127.0.0.1:{args.port}")
    os.environ.setdefault("ADOP_ALLOWED_ORIGIN", f"http://127.0.0.1:{args.port}")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ADOP Console: http://{args.host}:{args.port}")
    print("Control-plane backend:", os.getenv("ADOP_CONTROL_PLANE_BACKEND", "json"))
    server.serve_forever()


if __name__ == "__main__":
    main()
