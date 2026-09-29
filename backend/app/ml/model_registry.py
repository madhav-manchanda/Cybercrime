"""Model registry: versioned file-based artifacts + DB run/journal records.

Layout under ``ML_ARTIFACT_DIR``::

    var/ml/cashout-risk/1.0.0/model.joblib
    var/ml/cashout-risk/1.0.0/feature_columns.json
    var/ml/cashout-risk/1.0.0/metadata.json
    var/ml/cashout-risk/1.0.3/shard_*.joblib       # (future sharding)

Only ``ACTIVE`` artifacts are loaded for prediction; the registry also keeps a
JSON index so external tooling can inspect model lineage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import structlog

from app.core.config import settings
from app.core.enums import ModelKind, ModelStatus

logger = structlog.get_logger("ml.registry")

ARTIFACT_NAME = "model.joblib"
FEATURES_NAME = "feature_columns.json"
METADATA_NAME = "metadata.json"
INDEX_NAME = "registry.json"


class ModelRegistryError(RuntimeError):
    pass


class ModelRegistry:
    """Loads and saves versioned model artifacts."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.artifact_path).resolve()
        self._index_cache: dict[str, Any] | None = None

    # ----------------------------------------------------------- paths
    def model_dir(self, model_name: str, version: str) -> Path:
        return self.root / _safe(model_name) / version

    def artifact_path(self, model_name: str, version: str) -> Path:
        return self.model_dir(model_name, version) / ARTIFACT_NAME

    def features_path(self, model_name: str, version: str) -> Path:
        return self.model_dir(model_name, version) / FEATURES_NAME

    def metadata_path(self, model_name: str, version: str) -> Path:
        return self.model_dir(model_name, version) / METADATA_NAME

    # ---------------------------------------------------------- writes
    def save(
        self,
        model: Any,
        *,
        model_name: str,
        model_version: str,
        feature_version: str,
        model_kind: ModelKind,
        feature_columns: list[str],
        metadata: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Path:
        directory = self.model_dir(model_name, model_version)
        directory.mkdir(parents=True, exist_ok=True)

        artifact = self.artifact_path(model_name, model_version)
        joblib.dump(model, artifact)
        with self.features_path(model_name, model_version).open("w") as fh:
            json.dump(feature_columns, fh, indent=2)
        meta_payload = {
            "model_name": model_name,
            "model_version": model_version,
            "feature_version": feature_version,
            "model_kind": model_kind.value if hasattr(model_kind, "value") else str(model_kind),
            "saved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "artifact": str(artifact),
            "params": params or {},
            "extra": metadata or {},
        }
        with self.metadata_path(model_name, model_version).open("w") as fh:
            json.dump(meta_payload, fh, indent=2, default=str)
        self._update_index(model_name, model_version, meta_payload)
        logger.info("model_saved", name=model_name, version=model_version, path=str(artifact))
        return artifact

    # ---------------------------------------------------------- reads
    def load(self, model_name: str, model_version: str) -> Any:
        artifact = self.artifact_path(model_name, model_version)
        if not artifact.exists():
            raise ModelRegistryError(f"Artifact not found: {artifact}")
        return joblib.load(artifact)

    def load_feature_columns(self, model_name: str, model_version: str) -> list[str]:
        path = self.features_path(model_name, model_version)
        if not path.exists():
            raise ModelRegistryError(f"Feature manifest not found: {path}")
        with path.open() as fh:
            return json.load(fh)

    def load_metadata(self, model_name: str, model_version: str) -> dict[str, Any]:
        path = self.metadata_path(model_name, model_version)
        if not path.exists():
            return {}
        with path.open() as fh:
            return json.load(fh)

    # ------------------------------------------------------- discovery
    def list_versions(self, model_name: str) -> list[dict[str, Any]]:
        base = self.root / _safe(model_name)
        if not base.exists():
            return []
        versions: list[dict[str, Any]] = []
        for version_dir in sorted(base.iterdir(), reverse=True):
            meta_path = version_dir / METADATA_NAME
            if not meta_path.is_file():
                continue
            try:
                with meta_path.open() as fh:
                    meta = json.load(fh)
                meta["active"] = self._mark_active(model_name, version_dir.name, meta)
                versions.append(meta)
            except (json.JSONDecodeError, OSError):  # pragma: no cover
                continue
        return versions

    def active_version(self, model_name: str) -> str | None:
        versions = self.list_versions(model_name)
        for meta in versions:
            if meta.get("active"):
                return meta["model_version"]
        return versions[0]["model_version"] if versions else None

    @staticmethod
    def _mark_active(model_name: str, version: str, meta: dict[str, Any]) -> bool:
        status = meta.get("extra", {}).get("status", ModelStatus.ACTIVE.value)
        return status in {ModelStatus.ACTIVE.value, "candidate"} and meta.get("model_version") == version

    # ------------------------------------------------------------ index
    def _update_index(self, model_name: str, version: str, meta: dict[str, Any]) -> None:
        index: dict[str, Any] = self._load_index()
        index.setdefault(model_name, {})[version] = meta
        (self.root / INDEX_NAME).write_text(json.dumps(index, indent=2, default=str))

    def _load_index(self) -> dict[str, Any]:
        if self._index_cache is not None:
            return self._index_cache
        index_path = self.root / INDEX_NAME
        if index_path.exists():
            try:
                self._index_cache = json.loads(index_path.read_text())
            except json.JSONDecodeError:  # pragma: no cover
                self._index_cache = {}
        else:
            self._index_cache = {}
        return self._index_cache or {}

    def clear_cache(self) -> None:
        self._index_cache = None


def _safe(value: str) -> str:
    return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in value)


registry: ModelRegistry = ModelRegistry()

__all__ = ["ModelRegistry", "ModelRegistryError", "registry"]
