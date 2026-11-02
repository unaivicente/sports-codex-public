"""Dependency-free local HTTP API for the MVP frontend shell."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from apps.api.mock_payloads import (
    build_active_learning_queue_payload,
    build_correction_submission_payload,
    build_feedback_quality_payload,
    build_health_payload,
    build_mock_predictions_payload,
    build_ontology_payload,
    build_sports_payload,
    build_video_upload_payload,
)
from packages.contracts import ContractValidationError


class LocalApiHandler(BaseHTTPRequestHandler):
    """Serve local JSON endpoints consumed by the React shell."""

    server_version = "LocalSportsMetadataApi/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/health":
                self._send_json(build_health_payload())
                return

            if parsed.path == "/api/ontologies":
                self._send_json(build_ontology_payload())
                return

            if parsed.path == "/api/sports":
                self._send_json(build_sports_payload())
                return

            if parsed.path == "/api/feedback/quality":
                query = parse_qs(parsed.query)
                ontology_id = query.get("ontology_id", [None])[0]
                self._send_json(build_feedback_quality_payload(ontology_id))
                return

            if parsed.path == "/api/active-learning/queue":
                query = parse_qs(parsed.query)
                ontology_id = query.get("ontology_id", [None])[0]
                self._send_json(build_active_learning_queue_payload(ontology_id))
                return

            if parsed.path == "/api/predictions/mock":
                query = parse_qs(parsed.query)
                ontology_id = query.get("ontology_id", [None])[0]
                self._send_json(build_mock_predictions_payload(ontology_id))
                return
        except KeyError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            return

        self._send_json({"error": f"unknown endpoint {parsed.path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/api/videos":
                byte_count = self._discard_request_body()
                self._send_json(
                    build_video_upload_payload(
                        filename=self.headers.get("X-Local-Filename"),
                        content_type=self.headers.get("X-Local-Content-Type")
                        or self.headers.get("Content-Type"),
                        byte_count=byte_count,
                    ),
                    status=HTTPStatus.CREATED,
                )
                return

            if parsed.path == "/api/predictions/mock":
                payload = self._read_json_body()
                self._send_json(
                    build_mock_predictions_payload(
                        payload.get("ontology_id"),
                        video_id=payload.get("video_id"),
                    )
                )
                return

            if parsed.path == "/api/corrections":
                self._send_json(
                    build_correction_submission_payload(self._read_json_body()),
                    status=HTTPStatus.CREATED,
                )
                return
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"invalid JSON body: {exc.msg}"}, status=HTTPStatus.BAD_REQUEST)
            return
        except ContractValidationError as exc:
            self._send_json(
                {"error": "contract validation failed", "errors": exc.errors},
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except KeyError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            return

        self._send_json({"error": f"unknown endpoint {parsed.path}"}, status=HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Keep local dev logs compact while preserving request visibility."""

        print(f"{self.address_string()} - {format % args}")

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Local-Filename, X-Local-Content-Type")

    def _content_length(self) -> int:
        value = self.headers.get("Content-Length")
        if value is None:
            return 0
        try:
            return max(int(value), 0)
        except ValueError as exc:
            raise ValueError("invalid Content-Length header") from exc

    def _read_body_bytes(self) -> bytes:
        length = self._content_length()
        return self.rfile.read(length) if length else b""

    def _discard_request_body(self) -> int:
        remaining = self._content_length()
        total = remaining
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 64 * 1024))
            if not chunk:
                break
            remaining -= len(chunk)
        return total - remaining

    def _read_json_body(self) -> dict[str, Any]:
        body = self._read_body_bytes()
        if not body:
            return {}
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the local API server until interrupted."""

    server = ThreadingHTTPServer((host, port), LocalApiHandler)
    print(f"Local API listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local frontend shell API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
