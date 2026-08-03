# AI System Change Governance Tool

An executable implementation of the *"From AI System Change to Governance
Requirements"* framework: `Identify → Classify → Assess → Govern → Validate → Monitor`.

This is the "executable governance tool" described in Section 10 of the
framework write-up — a Streamlit app on top of a deterministic rules engine,
in the same architectural pattern as the existing Evaluator (Streamlit UI,
governance-frameworks-as-code).

## Status

This is a **v1 reference implementation**, consistent with the framework
write-up's own framing of the materiality dimensions and tier thresholds
as a starting point rather than a finished, validated standard. It
demonstrates that the framework is executable and testable, not that its
specific thresholds are calibrated to any institution's actual risk
appetite. Tier boundaries, gate definitions, and reviewer-routing hints
should be reviewed and adjusted before use in a real governance process.

The core classification path (triage → gates → dimension scoring →
tier → audit record, including overrides) has been manually tested
end-to-end. See "Extending it" below for known gaps that are out of
scope for v1.

## Files

| File | Purpose |
|---|---|
| `rules_engine.py` | Pure, deterministic classification/gate/scoring/tier logic. No LLM calls — this is the auditable core. |
| `app.py` | Streamlit UI walking through the 8 intake steps and rendering results. |
| `audit_store.py` | Minimal JSON-file audit trail (swap for a real DB in production). |
| `requirements.txt` | Python dependencies. |

## Design principle (Section 11)

The rules engine has **no model calls**. Per the framework: an LLM may be
used *elsewhere* to extract structured facts from a free-text change
description (e.g., "we're letting the agent auto-approve refunds under
$50" → `gate_2_human_review_removed = True`), but the classification,
escalation, and tier-routing logic itself must stay deterministic,
reproducible, and auditable. If you want to add that extraction layer,
have it populate the `ChangeSubmission` fields and always show the user
the extracted facts for confirmation/correction before `determine_tier()`
runs — never let the LLM call `determine_tier` for you.

## Core logic implemented

- **7 change domains / 33 evaluation units** (Section 4), pre-populated by
  3 triage questions (Section 3).
- **8 escalation gates** (Section 6.1) — 7 submission-time, 1
  detection-triggered (monitoring/incident/audit). Any triggered gate
  routes straight to **Tier 3**, non-compensating (no averaging against
  other dimensions).
- **5 scored impact dimensions** (Section 6.2), low/medium/high, only
  assessed when no gate is triggered. Conservative-first rule: any
  dimension at medium or high → **Tier 2**; all-low → **Tier 1**.
- **3 governance tiers** (Section 7) with their required activities.
- **Prior-evidence impact** (Section 6.3) captured separately from
  materiality, so validation scope stays targeted to the conclusions
  actually affected.
- **Reviewer routing hints** by triggered gate (Section 8/12) — e.g. a
  tool-write-access gate suggests Cybersecurity/Third-Party
  Risk/Operational Risk; a guardrail gate suggests
  Compliance/Legal/MRM.
- **Overrides** (Section 12): recorded against the original provisional
  outcome, never silently replacing it — `apply_override()` / the audit
  trail page always keep both the previous and new tier plus rationale
  and approver. Downward overrides (reducing the provisional tier) are
  held to Section 12's "stronger approval" requirement structurally: a
  second approver is required and the attempt is rejected without one.
  The audit-trail list view shows the effective (post-override) tier,
  flagged `(overridden)`, not just the original provisional one.
- **Audit trail** (Section 10, Step 8): every submission — facts, gate
  results, impact ratings, prior-evidence assessment, provisional
  outcome, and any override — is preserved as a JSON record, individually
  downloadable and exportable in bulk.

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Extending it — known gaps

- **LLM-assisted intake** *(not built)*: add a module that takes the
  user's free-text change description and pre-fills the triage
  checkboxes / gate checkboxes / suggested domains — always leaving them
  editable before `determine_tier()` is called. See "Design principle"
  above for the constraint this must respect.
- **Non-overridable gates** *(not built)*: Section 12 notes some gates
  may be designated non-overridable through ordinary review — e.g. a
  foundation-model-replacement gate that always requires governance
  committee sign-off no matter what a reviewer prefers. The current
  `apply_override()` enforces stronger approval on any downgrade, but
  does not yet block overrides on specific gates entirely. Add a
  role/gate check in `apply_override()` if you want certain gates locked
  against override regardless of approver count.
- **Real persistence**: replace `audit_store.py`'s JSON file with a
  database-backed store; the `load_all()` / `append()` / `update()`
  interface is deliberately small so the swap doesn't touch `app.py`.
- **Threshold tuning**: the framework flags the current tier-2 trigger
  (any single medium/high dimension) as a conservative v1 placeholder.
  If real Tier 2 volume warrants loosening it, that logic lives in one
  place — `determine_tier()` — and the change is auditable by diffing the
  function.
