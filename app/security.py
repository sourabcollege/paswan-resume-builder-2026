from __future__ import annotations

from flask import Flask


def init_security_headers(app: Flask) -> None:
    @app.after_request
    def apply_security_headers(response):
        configured_headers = app.config.get("SECURITY_HEADERS", {})
        for header, value in configured_headers.items():
            if value:
                response.headers[header] = value

        csp = app.config.get("CONTENT_SECURITY_POLICY")
        if csp:
            response.headers["Content-Security-Policy"] = csp

        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        if app.config.get("PREFERRED_URL_SCHEME") == "https" or app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        if response.mimetype == "text/html":
            response.headers.setdefault("Cache-Control", "no-store, max-age=0")

        return response


__all__ = ["init_security_headers"]
