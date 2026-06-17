from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


WarehouseEvidenceSource = Literal['canonical', 'observed', 'warehouse_report_only', 'unknown']
WarehouseEvidenceAvailability = Literal['unavailable', 'report_only']
WarehouseEvidenceLabel = Literal['report_only', 'needs_review', 'verify', 'unresolved', 'stale', 'blocked', 'unknown']
WarehouseEvidenceFreshnessStatus = Literal['fresh', 'stale', 'unknown']


class WarehousePlannerEvidenceItem(BaseModel):
    model_config = ConfigDict(extra='forbid')

    label: WarehouseEvidenceLabel
    source: WarehouseEvidenceSource
    summary: str


class WarehousePlannerEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    availability: WarehouseEvidenceAvailability
    report_only: Literal[True]
    manual_review_required: bool
    items: list[WarehousePlannerEvidenceItem]


class WarehousePlannerEvidenceFreshness(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: WarehouseEvidenceFreshnessStatus
    evaluated_at: str | None = None


class WarehousePlannerEvidenceSourceRun(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source_name: str | None = None
    run_key: str | None = None


class WarehousePlannerEvidenceContract(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['warehouse_planner_evidence/v1']
    system_id64: int
    generated_at: str
    freshness: WarehousePlannerEvidenceFreshness
    source_run: WarehousePlannerEvidenceSourceRun
    evidence_summary: WarehousePlannerEvidenceSummary
    warnings: list[str]
