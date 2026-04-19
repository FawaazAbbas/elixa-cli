"""
HTTP client for the Elixa API.

A thin typed wrapper around httpx. Three responsibilities:

  1. Attach auth (bearer token from `elixa login`, or an API key from the
     `ELIXA_API_KEY` env var) on every merchant-scoped call.
  2. Unwrap the backend's error envelope {code, detail, hint, request_id}
     into a structured ElixaAPIError so the CLI can pretty-print it.
  3. Surface clear messages when the server isn't reachable.

Every command in cli.py spins one up via a context manager, so socket
hygiene is automatic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from elixa import __version__
from elixa.config import Credentials, load_credentials, resolve_api_key_env, resolve_api_url

DEFAULT_TIMEOUT = 60.0


class ElixaAPIError(Exception):
    """Structured API failure. Mirrors the backend's error envelope."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        hint: str | None = None,
        request_id: str | None = None,
        body: Any = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint
        self.request_id = request_id
        self.body = body
        super().__init__(f"HTTP {status_code} {code}: {message}")


class ElixaClient:
    """Synchronous client for the Elixa REST API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        credentials: Credentials | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = resolve_api_url(base_url)
        self._creds = credentials if credentials is not None else load_credentials()
        self._api_key_env = resolve_api_key_env()
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": f"elixa-cli/{__version__}"},
        )

    # ── Context management ──────────────────────────────────────────

    def __enter__(self) -> "ElixaClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ── Auth ────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        # Explicit env key wins — lets CI override a stale `login`.
        if self._api_key_env:
            return {"Authorization": f"Bearer {self._api_key_env}"}
        if self._creds:
            return self._creds.auth_header()
        return {}

    def is_authenticated(self) -> bool:
        return bool(self._api_key_env or (self._creds and self._creds.is_authenticated()))

    # ── Transport ───────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = False,
        **kwargs: Any,
    ) -> Any:
        url = path if path.startswith("/") else f"/{path}"
        headers: dict[str, str] = kwargs.pop("headers", {}) or {}
        if auth:
            headers.update(self._auth_headers())
        try:
            r = self._client.request(method, url, headers=headers, **kwargs)
        except httpx.ConnectError as e:
            raise ElixaAPIError(
                status_code=0,
                code="network_unreachable",
                message=f"Could not connect to {self.base_url}.",
                hint="Is the server running? Check ELIXA_API_URL.",
                body=str(e),
            ) from e
        except httpx.TimeoutException as e:
            raise ElixaAPIError(
                status_code=0,
                code="timeout",
                message=f"Request to {self.base_url} timed out.",
                hint="Try again, or pass --timeout to raise the limit.",
                body=str(e),
            ) from e
        except httpx.RequestError as e:
            raise ElixaAPIError(
                status_code=0,
                code="request_error",
                message=str(e),
            ) from e

        if r.status_code >= 400:
            body: Any = r.text
            code = "error"
            message = r.reason_phrase or r.text
            hint: str | None = None
            request_id: str | None = None
            try:
                body = r.json()
                if isinstance(body, dict):
                    code    = body.get("code")    or code
                    message = body.get("detail")  or body.get("message") or message
                    hint    = body.get("hint")
                    request_id = body.get("request_id")
            except Exception:  # noqa: BLE001
                pass
            raise ElixaAPIError(
                status_code=r.status_code,
                code=code,
                message=str(message),
                hint=hint,
                request_id=request_id,
                body=body,
            )

        if r.status_code == 204 or not r.content:
            return None
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return r.text

    # ══════════════════════════════════════════════════════════════
    # Public surface (no auth required)
    # ══════════════════════════════════════════════════════════════

    def health(self) -> dict:
        return self._request("GET", "/v1/health")

    def search(self, q: str, **filters: Any) -> dict:
        params = {"q": q, **{k: v for k, v in filters.items() if v is not None}}
        return self._request("GET", "/v1/search", params=params)

    def get_product(self, elixa_id: str) -> dict:
        return self._request("GET", f"/v1/product/{elixa_id}")

    def list_merchants(self, q: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        return self._request("GET", "/v1/merchants", params=params)

    def get_schema(self) -> dict:
        return self._request("GET", "/v1/schema")

    # ══════════════════════════════════════════════════════════════
    # Merchant auth
    # ══════════════════════════════════════════════════════════════

    def login(self, email: str, password: str) -> dict:
        return self._request(
            "POST", "/v1/merchant/login",
            json={"email": email, "password": password},
        )

    def signup(self, *, email: str, password: str, merchant_name: str, merchant_domain: str) -> dict:
        return self._request(
            "POST", "/v1/merchant/signup",
            json={
                "email": email,
                "password": password,
                "merchant_name": merchant_name,
                "merchant_domain": merchant_domain,
            },
        )

    def me(self) -> dict:
        return self._request("GET", "/v1/merchant/me", auth=True)

    # ══════════════════════════════════════════════════════════════
    # Merchant-scoped (requires auth)
    # ══════════════════════════════════════════════════════════════

    # Products
    def list_my_products(self, **filters: Any) -> dict:
        params = {k: v for k, v in filters.items() if v is not None}
        return self._request("GET", "/v1/merchant/products", auth=True, params=params)

    # Analytics
    def analytics_summary(self, days: int = 30) -> dict:
        return self._request(
            "GET", "/v1/merchant/analytics/summary",
            auth=True, params={"days": days},
        )

    def top_queries(self, days: int = 30, limit: int = 10) -> list[dict]:
        return self._request(
            "GET", "/v1/merchant/analytics/top-queries",
            auth=True, params={"days": days, "limit": limit},
        )

    def top_products(self, days: int = 30, limit: int = 10) -> list[dict]:
        return self._request(
            "GET", "/v1/merchant/analytics/top-products",
            auth=True, params={"days": days, "limit": limit},
        )

    def events(self, event_type: str | None = None, limit: int = 50, offset: int = 0) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if event_type:
            params["event_type"] = event_type
        return self._request("GET", "/v1/merchant/analytics/events", auth=True, params=params)

    # API keys
    def list_api_keys(self) -> dict:
        return self._request("GET", "/v1/merchant/api-keys", auth=True)

    def create_api_key(self, *, name: str, scopes: list[str]) -> dict:
        return self._request(
            "POST", "/v1/merchant/api-keys",
            auth=True, json={"name": name, "scopes": scopes},
        )

    def revoke_api_key(self, key_id: str) -> None:
        self._request("DELETE", f"/v1/merchant/api-keys/{key_id}", auth=True)

    # Domain
    def get_domain_instructions(self) -> dict:
        return self._request("GET", "/v1/merchant/domain", auth=True)

    def verify_domain(self) -> dict:
        return self._request("POST", "/v1/merchant/domain/verify", auth=True)

    # ══════════════════════════════════════════════════════════════
    # Feed pushes (direct submit + registered sources)
    # ══════════════════════════════════════════════════════════════

    def submit_feed_json(
        self, *, merchant_name: str, merchant_domain: str, products: list[dict],
    ) -> dict:
        body = {
            "merchant_name": merchant_name,
            "merchant_domain": merchant_domain,
            "products": products,
        }
        return self._request("POST", "/v1/feed/submit", auth=True, json=body)

    def submit_feed_csv(
        self, file_path: Path, *, merchant_name: str, merchant_domain: str,
    ) -> dict:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "text/csv")}
            params = {"merchant_name": merchant_name, "merchant_domain": merchant_domain}
            return self._request(
                "POST", "/v1/feed/submit/csv",
                auth=True, files=files, params=params,
            )

    def register_feed_source(
        self,
        *,
        merchant_name: str,
        merchant_domain: str,
        feed_url: str,
        format: str | None = None,
        schedule_hours: int = 168,
    ) -> dict:
        body: dict[str, Any] = {
            "merchant_name":   merchant_name,
            "merchant_domain": merchant_domain,
            "feed_url":        feed_url,
            "schedule_hours":  schedule_hours,
        }
        if format:
            body["format"] = format
        return self._request("POST", "/v1/feeds/sources", auth=True, json=body)

    def list_feed_sources(self, active_only: bool = False, limit: int = 50, offset: int = 0) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if active_only:
            params["active_only"] = "true"
        return self._request("GET", "/v1/feeds/sources", auth=True, params=params)

    def get_feed_source(self, source_id: str) -> dict:
        return self._request("GET", f"/v1/feeds/sources/{source_id}", auth=True)

    def trigger_feed_fetch(self, source_id: str) -> dict:
        return self._request("POST", f"/v1/feeds/sources/{source_id}/fetch", auth=True)

    def delete_feed_source(self, source_id: str) -> None:
        self._request("DELETE", f"/v1/feeds/sources/{source_id}", auth=True)

    def update_feed_source(
        self,
        source_id: str,
        *,
        is_active: bool | None = None,
        schedule_hours: int | None = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if is_active is not None:
            params["is_active"] = "true" if is_active else "false"
        if schedule_hours is not None:
            params["schedule_hours"] = schedule_hours
        return self._request("PATCH", f"/v1/feeds/sources/{source_id}", auth=True, params=params)
