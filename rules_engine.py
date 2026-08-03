"""
rules_engine.py

Deterministic decision logic for the AI System Change Governance tool.

Implements the framework sequence:
    Identify -> Classify -> Assess -> Govern -> Validate -> Monitor

Design principle (per the framework, Section 11): an LLM may help extract
structured facts from a free-text change description, but the classification,
escalation, and tier-routing logic itself is deterministic, transparent, and
auditable. This module contains no model calls -- it is pure rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
import json
import uuid


# ---------------------------------------------------------------------------
# 1. Change domains & evaluation units (Section 4)
# ---------------------------------------------------------------------------

class ChangeDomain(str, Enum):
    BUSINESS_USE = "Business use"
    APPLICATION_LOGIC = "Application logic"
    KNOWLEDGE_AND_DATA = "Knowledge and data"
    FOUNDATION_MODEL = "Foundation model"
    TOOLS_AND_INTEGRATIONS = "Tools and integrations"
    INFERENCE_AND_EXECUTION = "Inference and execution"
    INFRASTRUCTURE_AND_OPERATIONS = "Infrastructure and operations"


EVALUATION_UNITS: Dict[ChangeDomain, List[str]] = {
    ChangeDomain.BUSINESS_USE: [
        "Use case or decision purpose",
        "Intended users or affected population",
        "Customer-facing functionality",
        "Degree of automation or autonomy",
    ],
    ChangeDomain.APPLICATION_LOGIC: [
        "Prompt construction",
        "Agent or workflow orchestration",
        "Business rules and decision thresholds",
        "Guardrails and output validation",
        "Human review, escalation, and overrides",
    ],
    ChangeDomain.KNOWLEDGE_AND_DATA: [
        "Retrieval sources and corpus",
        "Document preparation and chunking",
        "Embeddings and indexing",
        "Ranking and retrieval strategy",
        "Data lineage, access, and freshness",
    ],
    ChangeDomain.FOUNDATION_MODEL: [
        "Model family or version",
        "Model weights",
        "Fine-tuning or alignment",
        "Tokenizer",
        "Native capabilities and supported modalities",
    ],
    ChangeDomain.TOOLS_AND_INTEGRATIONS: [
        "Internal systems",
        "External APIs and services",
        "MCP tools and resources",
        "Permissions and authorization",
        "External models or agents",
    ],
    ChangeDomain.INFERENCE_AND_EXECUTION: [
        "Decoding and generation parameters",
        "Reasoning mode",
        "Context-window configuration",
        "Quantization",
        "Batching, caching, and serving optimization",
        "Runtime engine and provider configuration",
    ],
    ChangeDomain.INFRASTRUCTURE_AND_OPERATIONS: [
        "Deployment architecture",
        "Identity and access management",
        "Logging and monitoring",
        "Resilience and recovery",
        "Computing and storage platforms",
        "Release and configuration controls",
    ],
}

# Triage questions (Section 3) map onto domain groupings
TRIAGE_QUESTIONS = {
    "q1_foundation_model_changed": {
        "text": "Has the foundation model changed?",
        "domains": [ChangeDomain.FOUNDATION_MODEL],
    },
    "q2_application_changed": {
        "text": "Has the application using or controlling the model changed?",
        "domains": [ChangeDomain.APPLICATION_LOGIC, ChangeDomain.BUSINESS_USE],
    },
    "q3_environment_changed": {
        "text": "Has the environment around the application changed?",
        "domains": [
            ChangeDomain.KNOWLEDGE_AND_DATA,
            ChangeDomain.TOOLS_AND_INTEGRATIONS,
            ChangeDomain.INFERENCE_AND_EXECUTION,
            ChangeDomain.INFRASTRUCTURE_AND_OPERATIONS,
        ],
    },
}


# ---------------------------------------------------------------------------
# 2. Escalation gates (Section 6.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Gate:
    id: str
    description: str
    detection_triggered: bool = False  # True only for gate 8


GATES: List[Gate] = [
    Gate(
        "gate_1_foundation_model",
        "The foundation model is replaced, its weights are modified, or a "
        "model-version change alters capabilities, limitations, safety "
        "characteristics, supported modalities, or assumptions supporting "
        "the prior validation.",
    ),
    Gate(
        "gate_2_human_review_removed",
        "Mandatory human review or escalation is removed or materially "
        "weakened.",
    ),
    Gate(
        "gate_3_guardrail_weakened",
        "A safety, legal, or compliance guardrail is removed or materially "
        "weakened.",
    ),
    Gate(
        "gate_4_regulated_decision_threshold",
        "A business rule or decision threshold changes and affects a "
        "regulated or customer-facing decision.",
    ),
    Gate(
        "gate_5_new_use_case",
        "The system is applied to a new or materially changed use case, "
        "user population, or customer-facing function.",
    ),
    Gate(
        "gate_6_tool_write_access",
        "A new tool or API receives write, execute, approve, or "
        "data-transmission capability.",
    ),
    Gate(
        "gate_7_sensitive_data_expansion",
        "Access to sensitive or regulated data is materially expanded.",
    ),
    Gate(
        "gate_8_detection_triggered",
        "Monitoring detects substantive behavioral drift; an incident "
        "reveals a material failure mode not covered by the prior "
        "validation; a relied-upon assumption is disproven; or an "
        "unassessed downstream change is discovered.",
        detection_triggered=True,
    ),
]

GATES_BY_ID: Dict[str, Gate] = {g.id: g for g in GATES}


# ---------------------------------------------------------------------------
# 3. Scored impact dimensions (Section 6.2)
# ---------------------------------------------------------------------------

class ImpactBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ImpactDimension:
    id: str
    name: str
    question: str


IMPACT_DIMENSIONS: List[ImpactDimension] = [
    ImpactDimension(
        "behavioral",
        "Behavioral impact",
        "Could the change alter what the system outputs, decides, "
        "recommends, communicates, or does?",
    ),
    ImpactDimension(
        "business_regulatory",
        "Business-use and regulatory impact",
        "Could the change affect a consequential, regulated, or "
        "customer-facing use case, or change the degree to which the AI "
        "system influences an outcome?",
    ),
    ImpactDimension(
        "data",
        "Data impact",
        "Does the change introduce a new data source, expand data access, "
        "alter lineage or permitted use, or change the handling of "
        "sensitive data?",
    ),
    ImpactDimension(
        "control",
        "Control impact",
        "Could the change materially reduce the effectiveness of an "
        "existing control or make it easier to bypass (without meeting the "
        "full-removal gate threshold)?",
    ),
    ImpactDimension(
        "technical_operational",
        "Technical and operational impact",
        "Does the change introduce or materially alter a vendor "
        "dependency, integration, runtime behavior, operational "
        "resilience, detectability, or reversibility?",
    ),
]


# ---------------------------------------------------------------------------
# 4. Governance tiers (Section 7)
# ---------------------------------------------------------------------------

class Tier(str, Enum):
    TIER_1 = "Tier 1 — Administrative or limited"
    TIER_2 = "Tier 2 — Material"
    TIER_3 = "Tier 3 — Major"


TIER_REQUIREMENTS: Dict[Tier, List[str]] = {
    Tier.TIER_1: [
        "Documented change record",
        "Owner attestation",
        "Confirmation of no material behavioral, data, control, "
        "regulatory, or operational impact",
        "Lightweight first-line approval",
        "(No pre-deployment second-line review; subject to periodic "
        "risk-based sampling after the fact.)",
    ],
    Tier.TIER_2: [
        "Review by the relevant second-line function (e.g., MRM)",
        "Targeted regression, scenario, control, or integration testing "
        "scoped to the affected dimensions and evaluation units",
        "Updated documentation",
        "Assessment of prior-evidence impact",
        "Updated monitoring",
        "Approval before or according to defined deployment conditions",
    ],
    Tier.TIER_3: [
        "Full impact assessment",
        "Targeted or full revalidation based on prior-evidence impact",
        "Governance-committee or equivalent senior approval",
        "End-to-end and implementation testing",
        "Enhanced post-deployment monitoring",
        "Approval of residual risk",
        "Specialized Legal, Compliance, Privacy, Cybersecurity, "
        "Third-Party Risk, Operational Risk, or MRM review according to "
        "the gate triggered",
    ],
}

TIER_RANK: Dict[Tier, int] = {
    Tier.TIER_1: 1,
    Tier.TIER_2: 2,
    Tier.TIER_3: 3,
}

# Second-line function routing hints per triggered gate (Section 8 / 12)
GATE_REVIEWER_HINTS: Dict[str, List[str]] = {
    "gate_1_foundation_model": ["MRM"],
    "gate_2_human_review_removed": ["MRM", "Compliance", "Operational Risk"],
    "gate_3_guardrail_weakened": ["Compliance", "Legal", "MRM"],
    "gate_4_regulated_decision_threshold": ["Compliance", "Legal", "MRM"],
    "gate_5_new_use_case": ["Compliance", "MRM", "Business Line Risk"],
    "gate_6_tool_write_access": ["Cybersecurity", "Third-Party Risk", "Operational Risk"],
    "gate_7_sensitive_data_expansion": ["Privacy", "Cybersecurity"],
    "gate_8_detection_triggered": ["MRM", "Operational Risk"],
}


# ---------------------------------------------------------------------------
# 5. Submission & assessment data model
# ---------------------------------------------------------------------------

@dataclass
class ChangeDescription:
    current_state: str
    proposed_state: str
    business_rationale: str
    affected_system: str
    planned_deployment_date: str
    responsible_owner: str


@dataclass
class ChangeSubmission:
    description: ChangeDescription
    triage_answers: Dict[str, bool]                 # {"q1_foundation_model_changed": bool, ...}
    affected_domains: List[ChangeDomain]
    affected_evaluation_units: List[str]
    triggered_gates: List[str]                      # gate ids (excludes gate_8 unless detection)
    detection_triggered: bool = False                # gate 8
    detection_notes: str = ""
    impact_scores: Dict[str, ImpactBand] = field(default_factory=dict)  # only if no gate triggered
    prior_evidence_notes: str = ""


@dataclass
class GovernanceResult:
    tier: Tier
    gate_triggered: bool
    triggered_gate_ids: List[str]
    dimension_summary: Dict[str, str]
    required_activities: List[str]
    recommended_reviewers: List[str]
    rationale: str


@dataclass
class AuditRecord:
    record_id: str
    created_at: str
    submission: ChangeSubmission
    result: GovernanceResult
    reviewer_override: Optional[Dict] = None  # {"new_tier": ..., "rationale": ..., "approver": ...}

    def to_json(self) -> str:
        def _default(o):
            if isinstance(o, Enum):
                return o.value
            if hasattr(o, "__dict__"):
                return o.__dict__
            return str(o)
        return json.dumps(asdict(self), default=_default, indent=2)


# ---------------------------------------------------------------------------
# 6. Core deterministic logic
# ---------------------------------------------------------------------------

def determine_tier(submission: ChangeSubmission) -> GovernanceResult:
    """
    Applies Sections 6-7-11:
      - Any triggered submission-time gate, or the detection-triggered gate,
        routes directly to Tier 3 (non-compensating: no averaging against
        other dimensions).
      - Otherwise, conservative-first scoring: any dimension at medium/high
        escalates to Tier 2; all-low stays at Tier 1.
    """
    gate_triggered = bool(submission.triggered_gates) or submission.detection_triggered
    all_triggered_ids = list(submission.triggered_gates)
    if submission.detection_triggered and "gate_8_detection_triggered" not in all_triggered_ids:
        all_triggered_ids.append("gate_8_detection_triggered")

    reviewers: List[str] = []
    for gid in all_triggered_ids:
        reviewers.extend(GATE_REVIEWER_HINTS.get(gid, []))
    reviewers = sorted(set(reviewers)) if reviewers else []

    if gate_triggered:
        tier = Tier.TIER_3
        gate_descriptions = [GATES_BY_ID[g].description for g in all_triggered_ids if g in GATES_BY_ID]
        rationale = (
            "Escalation gate(s) triggered — provisional Tier 3 assigned "
            "without averaging against other dimensions:\n- "
            + "\n- ".join(gate_descriptions)
        )
        dimension_summary = {
            d.id: submission.impact_scores.get(d.id, ImpactBand.LOW).value
            if d.id in submission.impact_scores else "not scored (gate bypasses scoring)"
            for d in IMPACT_DIMENSIONS
        }
    else:
        if not submission.impact_scores:
            raise ValueError(
                "No gate triggered but no impact_scores provided — all five "
                "dimensions must be scored."
            )
        bands = [submission.impact_scores.get(d.id, ImpactBand.LOW) for d in IMPACT_DIMENSIONS]
        any_medium_or_high = any(b in (ImpactBand.MEDIUM, ImpactBand.HIGH) for b in bands)
        tier = Tier.TIER_2 if any_medium_or_high else Tier.TIER_1
        dimension_summary = {d.id: submission.impact_scores.get(d.id, ImpactBand.LOW).value for d in IMPACT_DIMENSIONS}
        if tier == Tier.TIER_2:
            triggered_dims = [
                d.name for d in IMPACT_DIMENSIONS
                if submission.impact_scores.get(d.id, ImpactBand.LOW) in (ImpactBand.MEDIUM, ImpactBand.HIGH)
            ]
            rationale = (
                "No escalation gate triggered. At least one impact dimension "
                "scored medium or higher, so the conservative-first rule "
                "routes to Tier 2: " + ", ".join(triggered_dims)
            )
            reviewers = ["MRM"]
        else:
            rationale = (
                "No escalation gate triggered and all five impact dimensions "
                "scored low. Tier 1 applies."
            )
            reviewers = []

    activities = list(TIER_REQUIREMENTS[tier])

    return GovernanceResult(
        tier=tier,
        gate_triggered=gate_triggered,
        triggered_gate_ids=all_triggered_ids,
        dimension_summary=dimension_summary,
        required_activities=activities,
        recommended_reviewers=reviewers,
        rationale=rationale,
    )


def new_record_id() -> str:
    return f"CHG-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def build_audit_record(submission: ChangeSubmission, result: GovernanceResult) -> AuditRecord:
    return AuditRecord(
        record_id=new_record_id(),
        created_at=datetime.now(timezone.utc).isoformat(),
        submission=submission,
        result=result,
    )


def apply_override(
    record: AuditRecord,
    new_tier: Tier,
    rationale: str,
    approver: str,
    second_approver: Optional[str] = None,
) -> AuditRecord:
    """
    Section 12: overrides must be limited to authorized roles, documented,
    recorded, reviewable, and subject to stronger approval when reducing
    the provisional tier. This function does not enforce role authorization
    (that belongs to the calling application / auth layer) -- but it does
    structurally enforce the stronger-approval-on-downgrade rule, and
    ensures every override is captured in the audit trail alongside the
    original provisional outcome.
    """
    previous_tier = record.result.tier
    is_downgrade = TIER_RANK[new_tier] < TIER_RANK[previous_tier]

    if is_downgrade and not second_approver:
        raise ValueError(
            "Downward override (reducing the provisional tier) requires a "
            "second approver per Section 12's stronger-approval rule."
        )

    record.reviewer_override = {
        "previous_tier": previous_tier.value,
        "new_tier": new_tier.value,
        "rationale": rationale,
        "approver": approver,
        "second_approver": second_approver,
        "is_downgrade": is_downgrade,
        "overridden_at": datetime.now(timezone.utc).isoformat(),
    }
    return record
