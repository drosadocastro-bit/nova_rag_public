import pytest

from core.safety.risk_assessment import RiskAssessment, RiskLevel
from nic_adversarial_test import ADVERSARIAL_TESTS


def _assert_refusal(assessment: dict) -> None:
    assert assessment.get("override_response"), "Expected refusal or block for unsafe query"


def _assert_allowed(assessment: dict) -> None:
    assert assessment.get("override_response") is None, "Unexpected refusal for valid query"
    assert assessment.get("risk_level") in {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}


# Sample a few questions per category to keep runtime reasonable
sampled = []
for cat_name, meta in ADVERSARIAL_TESTS.items():
    for q in meta["questions"][:3]:
        sampled.append((cat_name, meta["expected"], q))


@pytest.mark.parametrize("category,expected,question", sampled)
def test_adversarial_expected_behaviors(category: str, expected: str, question: str) -> None:
    assessment = RiskAssessment.assess_query(question)

    if expected in {"refuse", "refuse_or_correct", "refuse_or_cite", "low_confidence_or_refuse", "refuse_or_clarify"}:
        _assert_refusal(assessment)
    elif expected == "graceful_handling":
        assert assessment.get("risk_level")
    elif expected == "answer":
        _assert_allowed(assessment)
    else:
        pytest.skip(f"Unhandled expected behavior: {expected}")
