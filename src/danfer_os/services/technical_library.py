from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
import json
from pathlib import Path
from uuid import UUID

from danfer_os.models.technical_document import (
    DocumentCategory,
    DocumentCreate,
    DocumentUpdate,
    TechnicalDocument,
    RevisionRecord,
)


class DocumentNotFoundError(LookupError):
    pass


class TechnicalLibrary:
    """Catálogo em memória, isolado da camada HTTP e substituível por persistência."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._documents: dict[UUID, TechnicalDocument] = {}
        self._history: dict[UUID, list[RevisionRecord]] = {}
        self._lock = RLock()
        self._storage_path = storage_path
        self._load()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        self.restore(payload)

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(self.backup(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(self, data: DocumentCreate) -> TechnicalDocument:
        document = TechnicalDocument(**data.model_dump())
        with self._lock:
            if any(item.danfer_code == document.danfer_code for item in self._documents.values()):
                raise ValueError("código Danfer já cadastrado")
            self._documents[document.id] = document
            self._history[document.id] = []
            self._save()
        return document.model_copy(deep=True)

    def get(self, document_id: UUID) -> TechnicalDocument:
        with self._lock:
            document = self._documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document.model_copy(deep=True)

    def list(
        self,
        query: str | None = None,
        category: DocumentCategory | None = None,
        tag: str | None = None,
    ) -> list[TechnicalDocument]:
        needle = (query or "").strip().casefold()
        normalized_tag = (tag or "").strip().lower()
        with self._lock:
            documents = list(self._documents.values())
        if category:
            documents = [item for item in documents if item.category == category]
        if normalized_tag:
            documents = [item for item in documents if normalized_tag in item.tags]
        if needle:
            documents = [
                item
                for item in documents
                if needle in item.title.casefold()
                or needle in item.danfer_code.casefold()
                or needle in item.customer_code.casefold()
                or needle in item.customer.casefold()
                or needle in item.material.casefold()
                or needle in item.description.casefold()
                or any(needle in value.casefold() for value in item.tags)
            ]
        return [
            item.model_copy(deep=True)
            for item in sorted(documents, key=lambda value: value.title.casefold())
        ]

    def update(self, document_id: UUID, data: DocumentUpdate) -> TechnicalDocument:
        with self._lock:
            current = self._documents.get(document_id)
            if current is None:
                raise DocumentNotFoundError(document_id)
            changes = data.model_dump(exclude_unset=True)
            updated = current.model_copy(
                update={**changes, "updated_at": datetime.now(timezone.utc)}
            )
            self._documents[document_id] = updated
            self._history.setdefault(document_id, []).append(
                RevisionRecord(
                    changed_at=updated.updated_at,
                    reason=f"revisão {current.revision} → {updated.revision}",
                    previous=current,
                )
            )
            self._save()
        return updated.model_copy(deep=True)

    def delete(self, document_id: UUID) -> None:
        with self._lock:
            if self._documents.pop(document_id, None) is None:
                raise DocumentNotFoundError(document_id)
            self._history.pop(document_id, None)
            self._save()

    def history(self, document_id: UUID) -> list[RevisionRecord]:
        self.get(document_id)
        with self._lock:
            return [item.model_copy(deep=True) for item in self._history.get(document_id, [])]

    def backup(self) -> dict[str, object]:
        with self._lock:
            return {
                "version": 1,
                "documents": [item.model_dump(mode="json") for item in self._documents.values()],
                "history": {
                    str(key): [item.model_dump(mode="json") for item in values]
                    for key, values in self._history.items()
                },
            }

    def restore(self, payload: dict[str, object]) -> None:
        documents = [
            TechnicalDocument.model_validate(item)
            for item in payload.get("documents", [])  # type: ignore[union-attr]
        ]
        history_payload = payload.get("history", {})  # type: ignore[union-attr]
        with self._lock:
            self._documents = {item.id: item for item in documents}
            self._history = {
                UUID(key): [RevisionRecord.model_validate(item) for item in values]
                for key, values in history_payload.items()  # type: ignore[union-attr]
            }
            self._save()
