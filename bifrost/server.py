"""OpenAI-compatible HTTP front end (stdlib http.server).

Endpoints:
  GET  /health               -> {"status":"ok"}
  GET  /v1/models            -> proxies upstream model list
  POST /v1/chat/completions  -> never-refuse pipeline, OpenAI response shape

Streaming: if a client sends "stream": true, Bifrost runs the pipeline
non-streamed upstream (so it can detect/regenerate refusals) and then re-emits
the final answer as a single SSE delta followed by [DONE]. Clients that speak
the OpenAI streaming protocol still work; they just get one chunk.
"""
import json
import socketserver
import http.server
from typing import Any

from .config import Config
from . import upstream, pipeline


def make_handler(cfg: Config):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # quiet
            pass

        # ---- helpers ----
        def _cors(self):
            # Allow the browser front end (any origin) to call the API.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def _send_json(self, obj: Any, status: int = 200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _settings(self) -> dict[str, Any]:
            return {
                "enabled": cfg.enabled,
                "passthrough_harmful": cfg.passthrough_harmful,
                "model": cfg.default_model,
                "upstream": cfg.upstream_base,
            }

        def _error(self, status: int, message: str, etype: str = "bifrost_error"):
            self._send_json({"error": {"message": message, "type": etype}}, status)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw)

        # ---- routes ----
        def do_OPTIONS(self):
            # CORS preflight.
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path == "/health":
                self._send_json({"status": "ok", "upstream": cfg.upstream_base})
                return
            if self.path.rstrip("/") == "/settings":
                self._send_json(self._settings())
                return
            if self.path.rstrip("/") == "/v1/models":
                try:
                    self._send_json(upstream.list_models(cfg))
                except upstream.UpstreamError as e:
                    self._error(e.status, e.body or str(e), "upstream_error")
                return
            self._error(404, f"no such route: {self.path}", "not_found")

        def do_POST(self):
            if self.path.rstrip("/") == "/settings":
                try:
                    body = self._read_body()
                except Exception as e:
                    self._error(400, f"invalid JSON body: {e}", "invalid_request")
                    return
                # Runtime toggles: mutate the shared Config so the change takes
                # effect on the very next request (no restart needed).
                if "enabled" in body:
                    cfg.enabled = bool(body["enabled"])
                if "passthrough_harmful" in body:
                    cfg.passthrough_harmful = bool(body["passthrough_harmful"])
                self._send_json(self._settings())
                return
            if self.path.rstrip("/") != "/v1/chat/completions":
                self._error(404, f"no such route: {self.path}", "not_found")
                return
            try:
                payload = self._read_body()
            except Exception as e:
                self._error(400, f"invalid JSON body: {e}", "invalid_request")
                return
            if not payload.get("messages"):
                self._error(400, "'messages' is required", "invalid_request")
                return
            payload.setdefault("model", cfg.default_model)
            wants_stream = bool(payload.pop("stream", False))

            try:
                resp, _meta = pipeline.run(cfg, payload)
            except upstream.UpstreamError as e:
                self._error(e.status, e.body or str(e), "upstream_error")
                return
            except Exception as e:
                self._error(500, f"bifrost failure: {e}")
                return

            if wants_stream:
                self._send_stream(resp)
            else:
                self._send_json(resp)

        def _send_stream(self, resp: dict[str, Any]):
            """Re-emit a finished completion as a minimal OpenAI SSE stream."""
            try:
                msg = resp["choices"][0]["message"]
            except (KeyError, IndexError):
                msg = {"role": "assistant", "content": ""}
            chunk = {
                "id": resp.get("id", "bifrost"),
                "object": "chat.completion.chunk",
                "model": resp.get("model", cfg.default_model),
                "choices": [
                    {"index": 0, "delta": {"role": "assistant", "content": msg.get("content", "")},
                     "finish_reason": None}
                ],
            }
            done = {
                "id": resp.get("id", "bifrost"),
                "object": "chat.completion.chunk",
                "model": resp.get("model", cfg.default_model),
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for obj in (chunk, done):
                self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    return Handler


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(cfg: Config):
    cfg.validate()
    httpd = _Server((cfg.host, cfg.port), make_handler(cfg))
    print(
        f"[bifrost] listening on http://{cfg.host}:{cfg.port}  ->  upstream {cfg.upstream_base}\n"
        f"[bifrost] default model: {cfg.default_model}  | inject_system={cfg.inject_system} "
        f"max_retries={cfg.max_retries} passthrough_harmful={cfg.passthrough_harmful}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
