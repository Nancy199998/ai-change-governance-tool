import rules_engine as re_

desc = re_.ChangeDescription(
    current_state="test",
    proposed_state="test",
    business_rationale="test",
    affected_system="test",
    planned_deployment_date="test",
    responsible_owner="test",
)

submission = re_.ChangeSubmission(
    description=desc,
    triage_answers={},
    affected_domains=[],
    affected_evaluation_units=[],
    triggered_gates=[],
    detection_triggered=False,
    impact_scores={},
)

try:
    result = re_.determine_tier(submission)
    print("No error raised:", result)
except ValueError as e:
    print("Raised as expected:", e)