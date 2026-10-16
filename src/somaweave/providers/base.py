"""Provider abstraction: configuration, transport, rate limiting, caching.

A provider adapter turns one external knowledge source into canonical
``EvidenceRecord`` objects plus a ``SourceQueryResult`` describing the
outcome. Rules enforced here:

* ``Provider.query`` never raises. Transport failures, HTTP errors, malformed
  payloads and missing credentials are reported through ``SourceStatus``
  (``UNAVAILABLE``, ``ERROR``, ``NO_CREDENTIALS``) with a message; a query
  that succeeded with zero hits is ``NO_RECORDS``. None of the non-``OK``
  failure states may ever be read as negative evidence.
* Network access goes through an injectable ``transport`` callable so tests
  run fully offline against recorded payloads.
* API keys are read from the environment variable named in the config at
  call time and are never stored on the provider or written to results.
* No cluster-specific paths: the optional payload cache directory is passed
  in by the caller.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import EvidenceRecord, SourceQuery, SourceQueryResult, SourceStatus

DEFAULT_USER_AGENT = "somaweave/0.1 (research)"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProviderConfig(_Model):
    """Per-provider runtime configuration (no secrets)."""

    base_url: str = Field(description="Endpoint root, e.g. 'https://civicdb.org/api/graphql'.")
    timeout_s: float = Field(default=20.0, gt=0)
    rate_limit_per_s: float = Field(default=2.0, gt=0, description="Sustained request rate; token bucket.")
    burst: int = Field(default=1, ge=1, description="Token-bucket capacity.")
    user_agent: str = Field(default=DEFAULT_USER_AGENT)
    api_key_env: Optional[str] = Field(default=None, description="Name of the environment variable holding an API key. The key itself is never stored.")
    max_records: int = Field(default=25, ge=1, description="Maximum records returned per query.")
    enabled: bool = True


class TransportRequest(_Model):
    """Provider-neutral HTTP request handed to a transport."""

    method: str = Field(pattern=r"^(GET|POST)$")
    url: str
    params: dict[str, Any] = Field(default_factory=dict)
    json_body: Optional[dict[str, Any]] = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = 20.0

    def native_request(self, redact: Mapping[str, str] | None = None) -> str:
        """Canonical, deterministic text of the request for audit and cache keys.

        Values listed in ``redact`` (param name -> replacement) are masked so
        secrets never reach results or cache keys.
        """
        params = dict(self.params)
        for key, replacement in (redact or {}).items():
            if key in params:
                params[key] = replacement
        payload = {"method": self.method, "url": self.url, "params": params, "json": self.json_body}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class TransportResponse(_Model):
    status_code: int
    text: str
    headers: dict[str, str] = Field(default_factory=dict)

    def json(self) -> Any:  # type: ignore[override]
        return json.loads(self.text)


Transport = Callable[[TransportRequest], TransportResponse]


class TransportError(Exception):
    """Raised by a transport when no HTTP response was obtained (DNS, refused, timeout)."""


def requests_transport(request: TransportRequest) -> TransportResponse:
    """Default transport backed by ``requests``. Imported lazily so tests never need it."""
    import requests  # noqa: PLC0415 - lazy import keeps offline tests dependency-light

    try:
        resp = requests.request(
            request.method,
            request.url,
            params=request.params or None,
            json=request.json_body,
            headers=request.headers,
            timeout=request.timeout_s,
        )
    except requests.RequestException as exc:  # pragma: no cover - needs network
        raise TransportError(f"{type(exc).__name__}: {exc}") from exc
    return TransportResponse(status_code=resp.status_code, text=resp.text, headers=dict(resp.headers))


class RecordingTransport:
    """Wraps a transport and keeps every request/response pair.

    Used to refresh test fixtures from live services; ``dump`` writes the
    recorded exchanges as JSON that ``ScriptedTransport`` can replay.
    """

    def __init__(self, inner: Transport):
        self._inner = inner
        self.exchanges: list[dict[str, Any]] = []

    def __call__(self, request: TransportRequest) -> TransportResponse:
        response = self._inner(request)
        self.exchanges.append({
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "request": json.loads(request.native_request()),
            "response": {"status_code": response.status_code, "text": response.text},
        })
        return response

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.exchanges, indent=2) + "\n", encoding="utf-8")


class ScriptedTransport:
    """Replays recorded responses in order; raises ``TransportError`` when exhausted.

    Entries may be ``TransportResponse`` objects, ``Exception`` instances (raised
    when reached, to exercise failure paths) or recorded exchange dicts.
    """

    def __init__(self, script: list[Any]):
        self._script = list(script)
        self.requests: list[TransportRequest] = []

    @classmethod
    def from_fixture(cls, path: str | Path) -> "ScriptedTransport":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data if isinstance(data, list) else [data])

    def __call__(self, request: TransportRequest) -> TransportResponse:
        self.requests.append(request)
        if not self._script:
            raise TransportError("scripted transport exhausted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, TransportResponse):
            return item
        resp = item["response"]
        return TransportResponse(status_code=int(resp["status_code"]), text=resp["text"])


class TokenBucket:
    """Minimal thread-safe token bucket. ``clock``/``sleep`` are injectable for tests."""

    def __init__(self, rate_per_s: float, capacity: int = 1,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        if rate_per_s <= 0:
            raise ValueError("rate_per_s must be positive")
        self.rate = float(rate_per_s)
        self.capacity = float(max(1, capacity))
        self._tokens = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a token is available; return the seconds waited."""
        waited = 0.0
        with self._lock:
            while True:
                now = self._clock()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return waited
                need = (1.0 - self._tokens) / self.rate
                self._sleep(need)
                waited += need


class PayloadCache:
    """Stores raw provider payloads as JSON files keyed by sha256 of the native request.

    The root directory is supplied by the caller (for example from an
    environment variable read in the workflow layer); providers never read
    environment-specific paths themselves.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @staticmethod
    def key_for(native_request: str) -> str:
        return hashlib.sha256(native_request.encode("utf-8")).hexdigest()

    def _path(self, provider: str, key: str) -> Path:
        return self.root / provider / f"{key}.json"

    def reference(self, provider: str, key: str) -> str:
        return f"{provider}/{key}"

    def get(self, provider: str, key: str) -> Optional[dict[str, Any]]:
        path = self._path(provider, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, provider: str, key: str, native_request: str, payloads: list[Any]) -> str:
        path = self._path(provider, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "provider": provider,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "native_request": native_request,
            "payloads": payloads,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(envelope, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return self.reference(provider, key)


class Provider(ABC):
    """Base class for knowledge-source adapters.

    Subclasses implement ``_execute`` which may raise freely; ``query`` wraps it
    and converts every failure into an honest ``SourceQueryResult``.
    """

    name: str = "provider"
    requires_api_key: bool = False

    def __init__(self, config: ProviderConfig, transport: Transport | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.config = config
        self.transport: Transport = transport or requests_transport
        self._bucket = TokenBucket(config.rate_limit_per_s, config.burst, clock=clock, sleep=sleep)

    # -- credentials ---------------------------------------------------------
    def api_key(self) -> Optional[str]:
        """Read the API key from the configured environment variable at call time."""
        if not self.config.api_key_env:
            return None
        value = os.environ.get(self.config.api_key_env)
        return value or None

    # -- hooks for subclasses -------------------------------------------------
    @abstractmethod
    def version(self) -> Optional[str]:
        """Source release/version string if known before querying, else ``None``."""

    @abstractmethod
    def supports(self, plan_item: Any) -> bool:
        """Whether the provider can answer this plan item (tier and terms)."""

    @abstractmethod
    def _execute(self, plan_item: Any, query: SourceQuery, retrieved_at: datetime,
                 cache: PayloadCache | None) -> tuple[SourceQueryResult, list[EvidenceRecord]]:
        """Perform the native request(s) and map them. May raise."""

    # -- helpers ---------------------------------------------------------------
    def _send(self, request: TransportRequest) -> TransportResponse:
        """Rate-limited transport call; raises ``TransportError`` or ``HTTPStatusError``."""
        self._bucket.acquire()
        response = self.transport(request)
        if response.status_code >= 400:
            raise HTTPStatusError(response.status_code, response.text[:300])
        return response

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.config.user_agent, "Accept": "application/json"}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _result(self, query: SourceQuery, status: SourceStatus, retrieved_at: datetime, *,
                message: str | None = None, records: list[EvidenceRecord] | None = None,
                source_version: str | None = None, started: float | None = None) -> SourceQueryResult:
        records = records or []
        duration = None if started is None else max(0, int((time.monotonic() - started) * 1000))
        return SourceQueryResult(
            query=query, status=status, retrieved_at=retrieved_at, source_version=source_version,
            record_count=len(records), evidence_ids=[r.evidence_id for r in records],
            message=message, duration_ms=duration,
        )

    # -- public entry point ----------------------------------------------------
    def query(self, plan_item: Any, cache: PayloadCache | None = None) -> tuple[SourceQueryResult, list[EvidenceRecord]]:
        """Run one plan item against the source. Never raises."""
        started = time.monotonic()
        retrieved_at = self._now()
        query = SourceQuery(source_name=self.name, tier=plan_item.tier, query_terms=dict(plan_item.terms))
        if not self.config.enabled:
            return self._result(query, SourceStatus.NOT_QUERIED, retrieved_at, message="provider disabled in configuration", started=started), []
        if not self.supports(plan_item):
            return self._result(query, SourceStatus.NOT_SUPPORTED, retrieved_at, message=f"{self.name} does not support tier {plan_item.tier.value} with the given terms", started=started), []
        if self.requires_api_key and not self.api_key():
            env = self.config.api_key_env or "<unset>"
            return self._result(query, SourceStatus.NO_CREDENTIALS, retrieved_at, message=f"API key required; environment variable {env} is not set", started=started), []
        try:
            result, records = self._execute(plan_item, query, retrieved_at, cache)
        except TransportError as exc:
            return self._result(query, SourceStatus.UNAVAILABLE, retrieved_at, message=f"transport failure: {exc}", started=started), []
        except HTTPStatusError as exc:
            status = SourceStatus.UNAVAILABLE if exc.status_code >= 500 or exc.status_code == 429 else SourceStatus.ERROR
            if exc.status_code in (401, 403):
                status = SourceStatus.NO_CREDENTIALS
            return self._result(query, status, retrieved_at, message=f"HTTP {exc.status_code}: {exc.body}", started=started), []
        except Exception as exc:  # noqa: BLE001 - adapters must never propagate
            return self._result(query, SourceStatus.ERROR, retrieved_at, message=f"{type(exc).__name__}: {exc}", started=started), []
        if result.duration_ms is None:
            result = result.model_copy(update={"duration_ms": max(0, int((time.monotonic() - started) * 1000))})
        return result, records


class HTTPStatusError(Exception):
    """An HTTP response with status >= 400."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}")


class ProviderRegistry:
    """Name -> provider lookup with deterministic ordering."""

    def __init__(self, providers: list[Provider] | None = None):
        self._providers: dict[str, Provider] = {}
        for p in providers or []:
            self.register(p)

    def register(self, provider: Provider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"provider {provider.name!r} already registered")
        self._providers[provider.name] = provider

    def get(self, name: str) -> Optional[Provider]:
        return self._providers.get(name)

    def names(self) -> list[str]:
        return list(self._providers)

    def __contains__(self, name: object) -> bool:
        return name in self._providers

    def __len__(self) -> int:
        return len(self._providers)


def utc_date_version(moment: datetime) -> str:
    """Fallback version string for sources that expose no release identifier."""
    return f"retrieved:{moment.date().isoformat()}"
