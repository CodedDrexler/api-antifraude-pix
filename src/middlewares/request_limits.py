"""Bound request buffering before JSON parsing, including chunked bodies."""

from asyncio import timeout

from starlette.datastructures import Headers

from src.errors.handlers import error_response

MAX_REQUEST_BYTES = 32 * 1024
BODY_TIMEOUT_SECONDS = 10


class RequestLimitsMiddleware:
    def __init__(self, app, max_bytes=MAX_REQUEST_BYTES, timeout_seconds=BODY_TIMEOUT_SECONDS):
        self.app = app
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)

        async def fail(status, description, translation):
            response = error_response(
                status, f"PIX{status:06d}", "Request rejected", description, translation
            )
            await response(scope, receive, send)

        if scope["method"] == "POST" and scope["path"] == "/pix/transaction":
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return await fail(415, "Content-Type must be application/json", "Envie um corpo JSON")
        declared = headers.get("content-length")
        if declared is not None:
            if not declared.isascii() or not declared.isdigit():
                return await fail(400, "Invalid Content-Length", "Tamanho de requisição inválido")
            # Bound digit parsing as well as the declared body length.
            if len(declared) > 10 or int(declared) > self.max_bytes:
                return await fail(413, "Request body exceeds size limit", "Requisição muito grande")

        body = bytearray()
        try:
            async with timeout(self.timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > self.max_bytes:
                        return await fail(413, "Request body exceeds size limit", "Requisição muito grande")
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await fail(408, "Request body read timed out", "Tempo de envio esgotado")

        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
