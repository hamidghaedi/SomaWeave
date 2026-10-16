"""Knowledge-source adapters.

Each adapter maps one external source onto the canonical ``EvidenceRecord`` /
``SourceQueryResult`` types. This package never imports from retrieval,
interpretation, reporting or the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from somaweave.providers.base import (
    PayloadCache,
    Provider,
    ProviderConfig,
    ProviderRegistry,
    RecordingTransport,
    ScriptedTransport,
    Transport,
    TransportRequest,
    TransportResponse,
    requests_transport,
)
from somaweave.providers.civic import CivicProvider
from somaweave.providers.clinvar import ClinVarProvider
from somaweave.providers.europepmc import EuropePMCProvider
from somaweave.providers.oncokb import OncoKBConfig, OncoKBProvider

PROVIDER_CLASSES: dict[str, type[Provider]] = {
    CivicProvider.name: CivicProvider,
    ClinVarProvider.name: ClinVarProvider,
    EuropePMCProvider.name: EuropePMCProvider,
    OncoKBProvider.name: OncoKBProvider,
}


def config_model_for(name: str) -> type[ProviderConfig]:
    """Config model used to validate the entry for provider ``name``.

    Adapters that need extra secret-free settings declare a ``config_model``
    subclass of ``ProviderConfig``; everything else uses ``ProviderConfig``.
    """
    cls = PROVIDER_CLASSES.get(name)
    return getattr(cls, "config_model", ProviderConfig) if cls is not None else ProviderConfig


def load_provider_configs(path: str | Path) -> dict[str, ProviderConfig]:
    """Read a providers JSON file (``{"providers": {name: config}}``) into validated configs."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {name: config_model_for(name).model_validate(cfg) for name, cfg in (data.get("providers") or {}).items()}


def build_registry(configs: dict[str, ProviderConfig] | dict[str, dict[str, Any]],
                   transport: Transport | None = None) -> ProviderRegistry:
    """Instantiate every configured provider that has a known adapter.

    Unknown provider names raise ``KeyError`` so misconfiguration is loud.
    """
    registry = ProviderRegistry()
    for name, cfg in configs.items():
        cls = PROVIDER_CLASSES.get(name)
        if cls is None:
            raise KeyError(f"no provider adapter named {name!r}; known: {sorted(PROVIDER_CLASSES)}")
        config = cfg if isinstance(cfg, ProviderConfig) else config_model_for(name).model_validate(cfg)
        registry.register(cls(config, transport=transport))
    return registry


__all__ = [
    "CivicProvider", "ClinVarProvider", "EuropePMCProvider", "OncoKBConfig", "OncoKBProvider", "PROVIDER_CLASSES",
    "PayloadCache", "Provider", "ProviderConfig", "ProviderRegistry", "RecordingTransport", "ScriptedTransport",
    "Transport", "TransportRequest", "TransportResponse", "build_registry", "config_model_for", "load_provider_configs",
    "requests_transport",
]
