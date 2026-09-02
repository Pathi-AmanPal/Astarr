"""Pydantic v2 response models (PRD Section 6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EntitySummary(BaseModel):
    entity_id: str
    entity_name: str
    sector: str
    risk_score: int
    risk_score_raw: int
    capped: bool
    finding_count: int
    record_count: int


class Finding(BaseModel):
    finding_id: str
    rule_id: str
    finding_type: str
    title: str
    weight: int
    explanation: str


class EntityDetail(BaseModel):
    entity_id: str
    entity_name: str
    sector: str
    risk_score: int
    risk_score_raw: int
    capped: bool
    findings: list[Finding]


class Record(BaseModel):
    record_id: str
    entity_id: str
    asset_id: str
    severity: str
    category: str
    opened_at: datetime
    closed_at: datetime | None
    escalated: bool
    disposition: str
    investigation_notes: str | None
    closure_time_minutes: float | None


class Evidence(BaseModel):
    finding_id: str
    rule_id: str
    finding_type: str
    title: str
    weight: int
    explanation: str
    entity_id: str
    entity_name: str
    records: list[Record]


class ResetResult(BaseModel):
    status: str
    entities_loaded: int
    findings_generated: int


class Health(BaseModel):
    status: str
