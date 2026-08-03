"""
app.py

Streamlit front end for the AI System Change Governance tool.

Implements the 8-step process from Section 10 of the framework:
  1. Describe the change
  2. Identify affected domains and evaluation units
  3. Check escalation gates
  4. Assess the five impact dimensions (only if no gate triggered)
  5. Determine the provisional governance tier
  6. Assess prior-evidence impact
  7. Generate required activities
  8. Preserve the rationale (audit trail)

Run with:  streamlit run app.py
"""

import streamlit as st

import rules_engine as re_
import audit_store
from dataclasses import asdict

st.set_page_config(page_title="AI Change Governance Tool", layout="wide")

if "wizard" not in st.session_state:
    st.session_state.wizard = {}

W = st.session_state.wizard


def reset_wizard():
    st.session_state.wizard = {}


def _record_to_dict(record: "re_.AuditRecord") -> dict:
    import json
    return json.loads(record.to_json())


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

st.sidebar.title("AI Change Governance")
page = st.sidebar.radio("View", ["New change submission", "Audit trail / history"])
st.sidebar.markdown("---")
st.sidebar.caption(
    "Identify → Classify → Assess → Govern → Validate → Monitor\n\n"
    "Deterministic rules decide the tier. An LLM may help extract facts "
    "from free text, but never decides the outcome."
)

# ===========================================================================
# PAGE 1 — New change submission
# ===========================================================================

if page == "New change submission":
    st.title("New AI System Change Submission")

    if st.button("Start new submission", type="secondary"):
        reset_wizard()

    # --- Step 1: Describe the change ---------------------------------------
    st.header("Step 1 — Describe the change")
    col1, col2 = st.columns(2)
    with col1:
        current_state = st.text_area("Current state", W.get("current_state", ""))
        proposed_state = st.text_area("Proposed state", W.get("proposed_state", ""))
        business_rationale = st.text_area("Business rationale", W.get("business_rationale", ""))
    with col2:
        affected_system = st.text_input("Affected system / use case", W.get("affected_system", ""))
        planned_deployment_date = st.text_input(
            "Planned deployment date", W.get("planned_deployment_date", "")
        )
        responsible_owner = st.text_input("Responsible owner", W.get("responsible_owner", ""))

    W.update(
        current_state=current_state,
        proposed_state=proposed_state,
        business_rationale=business_rationale,
        affected_system=affected_system,
        planned_deployment_date=planned_deployment_date,
        responsible_owner=responsible_owner,
    )

    st.markdown("---")

    # --- Step 2: Identify affected domains and evaluation units -------------
    st.header("Step 2 — Identify affected domains and evaluation units")
    st.caption("Triage questions locate the broad source of the change. More than one 'yes' is expected.")

    triage_answers = {}
    for qid, q in re_.TRIAGE_QUESTIONS.items():
        triage_answers[qid] = st.checkbox(q["text"], value=W.get("triage", {}).get(qid, False), key=qid)
    W["triage"] = triage_answers

    suggested_domains = set()
    for qid, answered_yes in triage_answers.items():
        if answered_yes:
            suggested_domains.update(re_.TRIAGE_QUESTIONS[qid]["domains"])

    all_domain_values = [d.value for d in re_.ChangeDomain]
    default_domains = [d.value for d in suggested_domains] or W.get("affected_domains", [])
    affected_domain_values = st.multiselect(
        "Affected change domains (pre-populated from triage answers — adjust as needed)",
        options=all_domain_values,
        default=default_domains,
    )
    W["affected_domains"] = affected_domain_values

    affected_units = []
    for dv in affected_domain_values:
        domain = re_.ChangeDomain(dv)
        units = re_.EVALUATION_UNITS[domain]
        chosen = st.multiselect(
            f"Evaluation units — {dv}",
            options=units,
            default=[u for u in W.get("affected_units", []) if u in units],
            key=f"units_{dv}",
        )
        affected_units.extend(chosen)
    W["affected_units"] = affected_units

    st.markdown("---")

    # --- Step 3: Escalation gates --------------------------------------------
    st.header("Step 3 — Check escalation gates")
    st.caption(
        "A triggered gate routes directly to Tier 3 without averaging against "
        "other dimensions."
    )

    triggered_gates = []
    for gate in re_.GATES:
        if gate.detection_triggered:
            continue
        checked = st.checkbox(
            f"**{gate.id}** — {gate.description}",
            value=gate.id in W.get("triggered_gates", []),
            key=gate.id,
        )
        if checked:
            triggered_gates.append(gate.id)
    W["triggered_gates"] = triggered_gates

    st.markdown("**Detection-triggered gate (entered via monitoring/incident/audit, not owner submission):**")
    detection_triggered = st.checkbox(
        re_.GATES_BY_ID["gate_8_detection_triggered"].description,
        value=W.get("detection_triggered", False),
        key="gate_8",
    )
    detection_notes = ""
    if detection_triggered:
        detection_notes = st.text_area(
            "Detection notes (what was observed, source of detection)",
            W.get("detection_notes", ""),
        )
    W["detection_triggered"] = detection_triggered
    W["detection_notes"] = detection_notes

    gate_triggered_overall = bool(triggered_gates) or detection_triggered

    st.markdown("---")

    # --- Step 4: Impact dimensions (only if no gate triggered) ---------------
    impact_scores = {}
    if not gate_triggered_overall:
        st.header("Step 4 — Assess the five impact dimensions")
        st.caption("Any dimension scored medium or high routes the change to Tier 2 (conservative-first rule).")
        for dim in re_.IMPACT_DIMENSIONS:
            st.markdown(f"**{dim.name}** — {dim.question}")
            band = st.radio(
                f"Band — {dim.name}",
                options=[b.value for b in re_.ImpactBand],
                index=[b.value for b in re_.ImpactBand].index(
                    W.get("impact_scores", {}).get(dim.id, "low")
                ),
                key=f"dim_{dim.id}",
                horizontal=True,
                label_visibility="collapsed",
            )
            impact_scores[dim.id] = re_.ImpactBand(band)
        W["impact_scores"] = {k: v.value for k, v in impact_scores.items()}
    else:
        st.header("Step 4 — Assess the five impact dimensions")
        st.info("Skipped — an escalation gate is already triggered, so scoring is bypassed per the non-compensating rule.")
        impact_scores = {}

    st.markdown("---")

    # --- Step 6: Prior-evidence impact (kept ahead of activity generation) --
    st.header("Step 6 — Assess prior-evidence impact")
    prior_evidence_notes = st.text_area(
        "Which prior tests, assumptions, controls, or validation conclusions "
        "may no longer be sufficient?",
        W.get("prior_evidence_notes", ""),
    )
    W["prior_evidence_notes"] = prior_evidence_notes

    st.markdown("---")

    # --- Steps 5, 7, 8: Determine tier, generate activities, preserve --------
    st.header("Steps 5 & 7 — Provisional governance tier and required activities")

    can_run = bool(current_state and proposed_state and affected_system and responsible_owner)
    if not can_run:
        st.warning("Complete Step 1 (current state, proposed state, affected system, responsible owner) to run classification.")
    else:
        if st.button("Run classification", type="primary"):
            description = re_.ChangeDescription(
                current_state=current_state,
                proposed_state=proposed_state,
                business_rationale=business_rationale,
                affected_system=affected_system,
                planned_deployment_date=planned_deployment_date,
                responsible_owner=responsible_owner,
            )
            submission = re_.ChangeSubmission(
                description=description,
                triage_answers=triage_answers,
                affected_domains=[re_.ChangeDomain(d) for d in affected_domain_values],
                affected_evaluation_units=affected_units,
                triggered_gates=triggered_gates,
                detection_triggered=detection_triggered,
                detection_notes=detection_notes,
                impact_scores=impact_scores if not gate_triggered_overall else {},
                prior_evidence_notes=prior_evidence_notes,
            )
            try:
                result = re_.determine_tier(submission)
                W["result_ready"] = True
                W["_submission"] = submission
                W["_result"] = result
            except ValueError as e:
                st.error(str(e))
                W["result_ready"] = False

    if W.get("result_ready"):
        result: re_.GovernanceResult = W["_result"]
        submission: re_.ChangeSubmission = W["_submission"]

        tier_color = {
            re_.Tier.TIER_1: "green",
            re_.Tier.TIER_2: "orange",
            re_.Tier.TIER_3: "red",
        }[result.tier]

        st.markdown(f"### Provisional tier: :{tier_color}[{result.tier.value}]")
        st.write(result.rationale)

        if result.recommended_reviewers:
            st.write("**Recommended second-line reviewers:** " + ", ".join(result.recommended_reviewers))

        with st.expander("Impact dimension summary"):
            for k, v in result.dimension_summary.items():
                dim_name = next((d.name for d in re_.IMPACT_DIMENSIONS if d.id == k), k)
                st.write(f"- {dim_name}: **{v}**")

        st.markdown("#### Required activities")
        for activity in result.required_activities:
            st.write(f"- {activity}")

        st.markdown("---")
        st.header("Step 8 — Preserve the rationale")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Save to audit trail"):
                record = re_.build_audit_record(submission, result)
                audit_store.append(_record_to_dict(record))
                st.session_state["last_saved_id"] = record.record_id
                st.success(f"Saved as {record.record_id}")
        with col_b:
            preview_record = re_.build_audit_record(submission, result)
            st.download_button(
                "Download this record as JSON",
                data=preview_record.to_json(),
                file_name=f"{preview_record.record_id}.json",
                mime="application/json",
            )



# ===========================================================================
# PAGE 2 — Audit trail / history
# ===========================================================================

if page == "Audit trail / history":
    st.title("Audit trail")
    records = audit_store.load_all()

    if not records:
        st.info("No submissions recorded yet.")
    else:
        st.caption(f"{len(records)} recorded submission(s). Most recent first.")
        for rec in reversed(records):
            tier = rec["result"]["tier"]
            override = rec.get("reviewer_override")
            display_tier = override["new_tier"] if override else tier
            override_flag = " (overridden)" if override else ""
            owner = rec["submission"]["description"]["responsible_owner"]
            system = rec["submission"]["description"]["affected_system"]
            with st.expander(f"{rec['record_id']} — {display_tier}{override_flag} — {system} ({owner})"):
                st.write("**Current state:**", rec["submission"]["description"]["current_state"])
                st.write("**Proposed state:**", rec["submission"]["description"]["proposed_state"])
                st.write("**Rationale:**", rec["result"]["rationale"])
                st.write("**Required activities:**")
                for a in rec["result"]["required_activities"]:
                    st.write(f"- {a}")
                if rec.get("reviewer_override"):
                    st.warning(f"Overridden: {rec['reviewer_override']}")

                st.markdown("##### Reviewer override")
                override_tier = st.selectbox(
                    "New tier",
                    options=[t.value for t in re_.Tier],
                    index=[t.value for t in re_.Tier].index(tier),
                    key=f"override_tier_{rec['record_id']}",
                )
                current_rank = re_.TIER_RANK[re_.Tier(tier)]
                new_rank = re_.TIER_RANK[re_.Tier(override_tier)]
                is_downgrade = new_rank < current_rank

                override_rationale = st.text_area(
                    "Override rationale (required — must address the precise condition being overridden)",
                    key=f"override_rationale_{rec['record_id']}",
                )
                override_approver = st.text_input(
                    "Approver (authorized role)", key=f"override_approver_{rec['record_id']}"
                )

                override_second_approver = ""
                if is_downgrade:
                    st.warning(
                        "This reduces the provisional tier — per Section 12, downward "
                        "overrides require a second, stronger approval."
                    )
                    override_second_approver = st.text_input(
                        "Second approver (required for downward overrides)",
                        key=f"override_second_approver_{rec['record_id']}",
                    )

                if st.button("Apply override", key=f"apply_override_{rec['record_id']}"):
                    if not override_rationale or not override_approver:
                        st.error("Override rationale and approver are required.")
                    elif is_downgrade and not override_second_approver:
                        st.error("Downward overrides require a second approver.")
                    else:
                        rec["reviewer_override"] = {
                            "previous_tier": tier,
                            "new_tier": override_tier,
                            "rationale": override_rationale,
                            "approver": override_approver,
                            "second_approver": override_second_approver or None,
                            "is_downgrade": is_downgrade,
                        }
                        audit_store.update(rec["record_id"], rec)
                        st.success("Override recorded.")
                        st.rerun()

        st.markdown("---")
        st.download_button(
            "Download full audit trail (JSON)",
            data=__import__("json").dumps(records, indent=2),
            file_name="audit_trail_full.json",
            mime="application/json",
        )
