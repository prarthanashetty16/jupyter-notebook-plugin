"""Registered suggestion rules, one class per rule (Phase 5, pre-registration B1)."""

from __future__ import annotations

from nexus.suggestions.base import SuggestionRule
from nexus.suggestions.rules.dtypes import CategoryRule, DowncastRule, KeyDtypeRule
from nexus.suggestions.rules.read_csv import ReadCsvRule
from nexus.suggestions.rules.select_columns import SelectColumnsRule
from nexus.suggestions.rules.variables import CopyAvoidRule, DeleteVariablesRule

RULES: tuple[type[SuggestionRule], ...] = (
    SelectColumnsRule,
    DowncastRule,
    CategoryRule,
    KeyDtypeRule,
    ReadCsvRule,
    CopyAvoidRule,
    DeleteVariablesRule,
)
