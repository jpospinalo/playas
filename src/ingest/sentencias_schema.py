from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Section(BaseModel):
    title: str
    text: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field must not be empty or whitespace-only")
        return v


class Sentencia(BaseModel):
    source_file: str
    case_number: str
    judgement_date: str
    sections: List[Section]

    model_config = ConfigDict(extra="forbid")

    @field_validator("source_file", "case_number", "judgement_date")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field must not be empty or whitespace-only")
        return v

    @field_validator("judgement_date")
    @classmethod
    def valid_iso_date(cls, v: str) -> str:
        if not _DATE_RE.match(v):
            raise ValueError(f"judgement_date must be ISO YYYY-MM-DD, got: {v!r}")
        return v

    @model_validator(mode="after")
    def sections_not_empty(self) -> "Sentencia":
        if not self.sections:
            raise ValueError("sections must contain at least 1 element")
        return self
