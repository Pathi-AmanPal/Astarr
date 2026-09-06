"""Pydantic v2 response models (PRD Section 6).

`risk_score` is a float under the weighted-tier amendment to Section 5. It was an int
through Phase 1, when every score was an integer weight-sum; tier weighting produces
halves and quarters (56.5, 24.75, 13.5), so an int field would have silently truncated
or banker's-rounded them.

`tiers` is not decoration. Section 5 requires the score to be shown as a visible
breakdown a reader can foot for themselves, and under tier weighting the final number
no longer equals the sum of the finding weights on screen. The tier rows carry the
missing arithmetic.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TierScore(BaseModel):
    """One tier's contribution: raw sum, its individual cap, weight, and product."""

    tier: str
    raw: int
    capped_value: int
    capped: bool
    weight: float
    contribution: float


class EntitySummary(BaseModel):
    entity_id: str
    entity_name: str
    sector: str
    risk_score: float
    risk_score_raw: int
    capped: bool
    tiers: list[TierScore]
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
    risk_score: float
    risk_score_raw: int
    capped: bool
    tiers: list[TierScore]
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


class MlFeature(BaseModel):
    """One feature of one entity, with the peer-group figure it is judged against."""

    feature: str
    label: str
    value: float
    dataset_mean: float
    deviation: float
    contribution: float


class MlProfile(BaseModel):
    """The corroboration layer's working for a single entity.

    `available` is false when the layer could not run (fewer than two entities, or
    scikit-learn absent). The UI states that rather than rendering an empty panel that
    looks like "the model found nothing".
    """

    entity_id: str
    available: bool
    method: str
    anomalous: bool
    corroborated: bool
    peer_count: int
    features: list[MlFeature]


class DatasetInfo(BaseModel):
    """Which dataset the current schedule was computed over."""

    source: str          # 'upload' | 'empty'
    label: str
    loaded_at: datetime | None
    entity_count: int
    record_count: int


class ClearResult(BaseModel):
    status: str


class ResetResult(BaseModel):
    status: str
    entities_loaded: int
    findings_generated: int


class UploadResult(BaseModel):
    status: str
    label: str
    entities_loaded: int
    records_loaded: int
    findings_generated: int
    # Every column the parser had to translate, and every one it ignored. Empty when
    # the file already used the canonical names.
    mapping_notes: list[str] = []


class Health(BaseModel):
    status: str

