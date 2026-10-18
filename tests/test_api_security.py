import asyncio
import json

import pytest
from conftest import request
from fastapi import FastAPI

from src.middlewares.request_context import register_request_middleware
from src.middlewares.request_limits import MAX_REQUEST_BYTES, RequestLimitsMiddleware


def exercise(app, *, headers=(), chunks=(b"{}",), path="/pix/transaction", method="POST", delay=0):
    async def run():
        sent, reads = [], []
        parts = iter(chunks)

        async def receive():
            reads.append(True)
            if delay:
                await asyncio.sleep(delay)
            try:
                chunk = next(parts)
                return {"type": "http.request", "body": chunk, "more_body": True}
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": list(headers),
                "server": ("localhost", 8000),
                "client": ("127.0.0.1", 1234),
            },
            receive,
            send,
        )
        start = next(m for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return start["status"], dict(start["headers"]), json.loads(body), len(reads)

    return asyncio.run(run())


def endpoint_app():
    app = FastAPI()

    @app.post("/pix/transaction")
    def echo(body: dict):
        return body

    return app


@pytest.mark.parametrize("declared", [None, b"1", str(MAX_REQUEST_BYTES + 1).encode()])
def test_size_limit_counts_actual_chunks_even_without_or_with_false_content_length(declared):
    headers = [(b"content-type", b"application/json")]
    if declared is not None:
        headers.append((b"content-length", declared))
    result = exercise(
        RequestLimitsMiddleware(endpoint_app()), headers=headers, chunks=(b" " * 20_000, b" " * 20_000)
    )
    assert result[0] == 413
    assert result[2]["code"] == "PIX000413"
    if declared is not None and int(declared) > MAX_REQUEST_BYTES:
        assert result[3] == 0


def test_exact_size_limit_preserves_body_for_validation():
    body = b'{"data":"' + b"x" * (MAX_REQUEST_BYTES - 11) + b'"}'
    assert len(body) == MAX_REQUEST_BYTES
    result = exercise(
        RequestLimitsMiddleware(endpoint_app()),
        headers=[(b"content-type", b"application/json; charset=utf-8")],
        chunks=(body,),
    )
    assert result[0] == 200
    assert len(result[2]["data"]) == MAX_REQUEST_BYTES - 11


@pytest.mark.parametrize("content_type", [None, b"text/plain", b"application/xml"])
def test_pix_requires_json_content_type(content_type):
    headers = [] if content_type is None else [(b"content-type", content_type)]
    result = exercise(RequestLimitsMiddleware(endpoint_app()), headers=headers)
    assert result[0] == 415
    assert result[3] == 0


@pytest.mark.parametrize("declared", [b"-1", b"NaN", b"1.5", b"+2"])
def test_malformed_content_length_is_rejected(declared):
    result = exercise(
        RequestLimitsMiddleware(endpoint_app()),
        headers=[
            (b"content-type", b"application/json"),
            (b"content-length", declared),
        ],
    )
    assert result[0] == 400


def test_body_read_has_total_deadline():
    result = exercise(
        RequestLimitsMiddleware(endpoint_app(), timeout_seconds=0.001),
        headers=[(b"content-type", b"application/json")],
        delay=0.02,
    )
    assert result[0] == 408


@pytest.mark.parametrize("token", [None, b"wrong-token"])
def test_request_without_internal_token_reaches_endpoint_and_sets_security_headers(token):
    app = endpoint_app()
    app.add_middleware(RequestLimitsMiddleware)
    register_request_middleware(app)
    request_headers = [(b"content-type", b"application/json")]
    if token is not None:
        request_headers.append((b"internal-token", token))
    status, headers, body, reads = exercise(app, headers=request_headers, chunks=(b'{"ok":true}',))
    assert status == 200
    assert reads > 0
    assert body == {"ok": True}
    assert headers[b"cache-control"] == b"no-store"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert b"x-request-id" in headers


def test_unhandled_error_does_not_leak_exception_details_and_is_correlated(caplog):
    app = FastAPI()

    @app.get("/fail")
    def fail():
        raise RuntimeError("sensitive-sql-password-and-document")

    register_request_middleware(app)
    status, headers, body, _ = exercise(app, path="/fail", method="GET")
    assert status == 500
    assert body["code"] == "PIX000500"
    assert "sensitive-sql-password-and-document" not in json.dumps(body) + caplog.text
    assert headers[b"x-request-id"].decode() in caplog.text
    assert "RuntimeError" in caplog.text
    assert headers[b"cache-control"] == b"no-store"


def test_success_and_not_found_http_responses_prohibit_caching(payload):
    for method, path, body in [
        ("POST", "/pix/transaction", payload),
        ("GET", "/pix/transaction/" + payload["id"], None),
        ("GET", "/pix/transaction/missing-security-test", None),
    ]:
        _, _, headers = request(method, path, body)
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"


def test_oversized_http_request_does_not_consume_transaction_id(payload):
    payload["excess"] = "x" * MAX_REQUEST_BYTES
    status, response, headers = request("POST", "/pix/transaction", payload)
    assert status == 413
    assert response["code"] == "PIX000413"
    assert headers["Cache-Control"] == "no-store"
    assert request("GET", "/pix/transaction/" + payload["id"])[0] == 404
