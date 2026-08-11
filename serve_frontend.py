#!/usr/bin/env python3
"""Proxy server that serves frontend/dist and proxies API requests to backend.

.. deprecated::
    This script is no longer meant to be started directly.  Launch it
    through ``startserver.py`` instead::

        python startserver.py --proxy

    The proxy server is now a managed child of ``startserver.py``; when
    ``startserver.py`` exits, the proxy server is terminated automatically.
"""
import os
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import subprocess
import sys

FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"
BACKEND_URL = "http://localhost:8000"


class ProxyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_proxy(self, path):
        try:
            url = BACKEND_URL + path
            req = urllib.request.Request(url, method=self.command)
            for header in self.headers:
                if header.lower() not in ("host", "connection", "content-length"):
                    req.add_header(header, self.headers[header])
            content_length = self.headers.get("Content-Length")
            if content_length and self.command in ("POST", "PUT", "PATCH"):
                body = self.rfile.read(int(content_length))
                with urllib.request.urlopen(req, data=body) as resp:
                    self._send_response(resp)
            else:
                with urllib.request.urlopen(req) as resp:
                    self._send_response(resp)
        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")

    def _send_response(self, resp):
        try:
            self.send_response(resp.status)
            for header, value in resp.getheaders():
                if header.lower() not in ("transfer-encoding", "content-encoding", "content-length", "connection"):
                    self.send_header(header, value)
            self.end_headers()
            self.wfile.write(resp.read())
        except BrokenPipeError:
            pass
        except ConnectionAbortedError:
            pass

    def _send_response(self, resp):
        self.send_response(resp.status)
        for header, value in resp.getheaders():
            if header.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                self.send_header(header, value)
        self.end_headers()
        self.wfile.write(resp.read())

    def do_GET(self):
        if self.path.startswith("/api/"):
            self.do_proxy(self.path)
        elif self.path.startswith("/ws/"):
            self.send_error(501, "WebSocket proxy not supported in this server. Install Node.js for full functionality.")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/") or self.path.startswith("/ws/"):
            self.do_proxy(self.path)
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PUT(self):
        if self.path.startswith("/api/") or self.path.startswith("/ws/"):
            self.do_proxy(self.path)
        else:
            self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        if self.path.startswith("/api/") or self.path.startswith("/ws/"):
            self.do_proxy(self.path)
        else:
            self.send_error(405, "Method Not Allowed")


def main():
    port = 5173
    print("  This script is deprecated as a standalone entry point.")
    print("  Starting via: python startserver.py --proxy")
    server = HTTPServer(("0.0.0.0", port), ProxyHandler)
    print(f"Serving frontend from {FRONTEND_DIR} on http://localhost:{port}")
    print(f"Proxying /api and /ws to {BACKEND_URL}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
        server.server_close()


if __name__ == "__main__":
    main()
