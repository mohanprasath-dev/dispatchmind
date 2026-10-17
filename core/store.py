"""Unified storage interface supporting Firestore and local JSON file fallback."""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from core.config import (
    DEMO_MODE,
    FIRESTORE_PROJECT_ID,
    GOOGLE_CLOUD_PROJECT,
    LOCAL_STORE_PATH,
    ROOT_DIR,
)

logger = logging.getLogger(__name__)

SUPPORTED_COLLECTIONS = [
    "orders",
    "vehicles",
    "drivers",
    "routes",
    "events",
    "tuning",
    "messages",
    "pod",
]


def _serialize_data(data: Any) -> Dict[str, Any]:
    """Serialize Pydantic models or dicts to a json-compatible dict."""
    if isinstance(data, BaseModel):
        return data.model_dump()
    if isinstance(data, dict):
        return data.copy()
    raise ValueError(f"Expected dict or BaseModel, got {type(data).__name__}")


class StoreInterface(ABC):
    """Abstract storage interface for all collections."""

    @abstractmethod
    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document by ID."""
        pass

    @abstractmethod
    def set(self, collection: str, doc_id: str, data: Any) -> None:
        """Create or replace a document by ID."""
        pass

    @abstractmethod
    def update(self, collection: str, doc_id: str, data: Dict[str, Any]) -> None:
        """Partially update fields in an existing document."""
        pass

    @abstractmethod
    def delete(self, collection: str, doc_id: str) -> bool:
        """Delete a document by ID."""
        pass

    @abstractmethod
    def list(
        self,
        collection: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """List documents in a collection with optional key-value filters."""
        pass

    @abstractmethod
    def clear(self, collection: Optional[str] = None) -> None:
        """Clear documents in a specific collection or all collections."""
        pass


BaseStore = StoreInterface


class LocalJsonStore(StoreInterface):
    """Thread-safe JSON file store for DEMO_MODE and offline execution."""

    def __init__(
        self,
        file_path: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ):
        if file_path:
            self.file_path = Path(file_path)
        elif base_dir:
            b = Path(base_dir)
            if b.suffix == ".json":
                self.file_path = b
            else:
                self.file_path = b / "local_store.json"
        else:
            self.file_path = LOCAL_STORE_PATH

        self._lock = Lock()
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {
            c: {} for c in SUPPORTED_COLLECTIONS
        }
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.file_path.exists():
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            for col in SUPPORTED_COLLECTIONS:
                                if col in loaded and isinstance(loaded[col], dict):
                                    self._data[col] = loaded[col]
                except Exception as exc:
                    logger.warning("Failed to load local store from %s: %s", self.file_path, exc)
            else:
                self._save_unlocked()

    def _save_unlocked(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.file_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False, default=str)
        tmp_path.replace(self.file_path)

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            col = self._data.get(collection, {})
            item = col.get(str(doc_id))
            return item.copy() if item is not None else None

    def set(self, collection: str, doc_id: str, data: Any) -> None:
        clean_data = _serialize_data(data)
        doc_key = str(doc_id)
        if "id" not in clean_data:
            clean_data["id"] = doc_key

        with self._lock:
            if collection not in self._data:
                self._data[collection] = {}
            self._data[collection][doc_key] = clean_data
            self._save_unlocked()

    def update(self, collection: str, doc_id: str, data: Dict[str, Any]) -> None:
        doc_key = str(doc_id)
        with self._lock:
            if collection not in self._data or doc_key not in self._data[collection]:
                raise KeyError(f"Document {doc_key} not found in collection {collection}")
            self._data[collection][doc_key].update(data)
            self._save_unlocked()

    def delete(self, collection: str, doc_id: str) -> bool:
        doc_key = str(doc_id)
        with self._lock:
            if collection in self._data and doc_key in self._data[collection]:
                del self._data[collection][doc_key]
                self._save_unlocked()
                return True
            return False

    def list(
        self,
        collection: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            col = self._data.get(collection, {})
            items = list(col.values())

        if not filters:
            return [item.copy() for item in items]

        results = []
        for item in items:
            matches = True
            for k, v in filters.items():
                if item.get(k) != v:
                    matches = False
                    break
            if matches:
                results.append(item.copy())
        return results

    def clear(self, collection: Optional[str] = None) -> None:
        with self._lock:
            targets = [collection] if collection else list(SUPPORTED_COLLECTIONS)
            for col in targets:
                self._data[col] = {}
            self._save_unlocked()


JSONStore = LocalJsonStore


class FirestoreStore(StoreInterface):
    """Google Cloud Firestore storage implementation."""

    def __init__(self, project_id: Optional[str] = None):
        try:
            from google.cloud import firestore  # type: ignore

            project = project_id or FIRESTORE_PROJECT_ID or GOOGLE_CLOUD_PROJECT
            self.db = firestore.Client(project=project) if project else firestore.Client()
        except Exception as exc:
            logger.error("Failed to initialize Firestore client: %s", exc)
            raise

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db.collection(collection).document(str(doc_id)).get()
        if doc.exists:
            d = doc.to_dict() or {}
            d.setdefault("id", str(doc_id))
            return d
        return None

    def set(self, collection: str, doc_id: str, data: Any) -> None:
        clean_data = _serialize_data(data)
        doc_key = str(doc_id)
        if "id" not in clean_data:
            clean_data["id"] = doc_key
        self.db.collection(collection).document(doc_key).set(clean_data)

    def update(self, collection: str, doc_id: str, data: Dict[str, Any]) -> None:
        self.db.collection(collection).document(str(doc_id)).update(data)

    def delete(self, collection: str, doc_id: str) -> bool:
        self.db.collection(collection).document(str(doc_id)).delete()
        return True

    def list(
        self,
        collection: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        query = self.db.collection(collection)
        if filters:
            from google.cloud import firestore  # type: ignore

            for k, v in filters.items():
                query = query.where(filter=firestore.FieldFilter(k, "==", v))

        docs = query.stream()
        results: List[Dict[str, Any]] = []
        for doc in docs:
            d = doc.to_dict() or {}
            d.setdefault("id", doc.id)
            results.append(d)
        return results

    def clear(self, collection: Optional[str] = None) -> None:
        targets = [collection] if collection else list(SUPPORTED_COLLECTIONS)
        for col in targets:
            docs = self.db.collection(col).list_documents()
            for doc in docs:
                doc.delete()


def get_store(
    demo_mode: Optional[bool] = None,
    file_path: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> StoreInterface:
    """Provide storage instance based on configuration and availability."""
    is_demo = DEMO_MODE if demo_mode is None else demo_mode

    if is_demo or not (FIRESTORE_PROJECT_ID or GOOGLE_CLOUD_PROJECT):
        return LocalJsonStore(file_path=file_path, base_dir=base_dir)

    try:
        return FirestoreStore()
    except Exception as exc:
        logger.warning("Firestore unavailable (%s). Falling back to LocalJsonStore.", exc)
        return LocalJsonStore(file_path=file_path, base_dir=base_dir)


# Module-level singleton instance for general import
store: StoreInterface = get_store()
