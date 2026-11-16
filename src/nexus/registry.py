"""Registry of operation models (decorator-based registration)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TypeVar

from nexus.analyzer import DetectedOp
from nexus.models.base import OperationModel

log = logging.getLogger("nexus")

M = TypeVar("M", bound=type[OperationModel])


class ModelRegistry:
    """Holds one instance per model name."""

    def __init__(self) -> None:
        self._models: dict[str, OperationModel] = {}

    def register(self, cls: M) -> M:
        """Class decorator: instantiate ``cls()`` and add it."""
        self.add(cls())
        return cls

    def add(self, model: OperationModel) -> None:
        if model.name in self._models:
            raise ValueError(f"model {model.name!r} is already registered")
        self._models[model.name] = model

    def remove(self, name: str) -> None:
        del self._models[name]

    def get(self, name: str) -> OperationModel | None:
        return self._models.get(name)

    def find(self, op: DetectedOp) -> list[OperationModel]:
        """Models that match ``op``; a model whose ``matches`` raises is skipped."""
        found = []
        for model in self._models.values():
            try:
                if model.matches(op):
                    found.append(model)
            except Exception:
                log.debug("nexus: %s.matches raised", model.name, exc_info=True)
        return found

    def __iter__(self) -> Iterator[OperationModel]:
        return iter(self._models.values())

    def __len__(self) -> int:
        return len(self._models)


default_registry = ModelRegistry()
register_model = default_registry.register
