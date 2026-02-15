from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ComputedColumn(BaseModel):
    name: str
    expr: str

    @field_validator("name", "expr")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value cannot be empty.")
        return value


class ColumnConfig(BaseModel):
    order: list[str] = Field(default_factory=lambda: ["path"])
    hidden: list[str] = Field(default_factory=list)
    alias: dict[str, str] = Field(default_factory=dict)
    computed: list[ComputedColumn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_alias_and_computed(self) -> "ColumnConfig":
        alias_values = [alias for alias in self.alias.values() if alias.strip()]
        if len(alias_values) != len(set(alias_values)):
            raise ValueError("Alias names must be unique.")

        computed_names = [item.name for item in self.computed]
        if len(computed_names) != len(set(computed_names)):
            raise ValueError("Computed column names must be unique.")
        return self


class SortConfig(BaseModel):
    by: str | None = None
    direction: Literal["asc", "desc"] = "asc"


class RowConfig(BaseModel):
    pinned_ids: list[str] = Field(default_factory=list)
    sort: SortConfig = Field(default_factory=SortConfig)


class ViewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    pattern: str
    columns: ColumnConfig = Field(default_factory=ColumnConfig)
    rows: RowConfig = Field(default_factory=RowConfig)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("View name cannot be empty.")
        if "/" in name or "\\" in name:
            raise ValueError("View name cannot include path separators.")
        return name

    @field_validator("pattern")
    @classmethod
    def _validate_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc
        return value


class ScanRequest(BaseModel):
    view: ViewConfig | None = None
