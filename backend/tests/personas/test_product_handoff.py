"""Generic persona handoffs require explicit prototype and relevant coverage."""
import pytest

from backend.app.features.personas.product_handoff import HandoffError, consume_product_handoff
from backend.tests.prototype_fixtures import handoff, quota


def test_generic_catalog_binds_without_claiming_trials_or_runtime():
    binding = consume_product_handoff(candidate=handoff(), quotas=[quota()])
    assert binding.tasks()[0].check_id == 'normal-v1'
    assert binding.quotas()[0].count == 500
    assert binding.report()['runtime_verified'] is False
    assert binding.report()['completed_trials'] == 0
    assert binding == consume_product_handoff(candidate=handoff(), quotas=[quota()])


def test_draft_and_missing_audience_coverage_fail_closed():
    draft = handoff()
    draft.version.status='draft'
    with pytest.raises(HandoffError):
        consume_product_handoff(candidate=draft, quotas=[quota()])
    with pytest.raises(HandoffError):
        consume_product_handoff(candidate=handoff(), quotas=[])


def test_missing_state_and_over_budget_check_are_rejected():
    catalog=handoff()
    catalog.initial_states={}
    with pytest.raises(HandoffError):
        consume_product_handoff(candidate=catalog, quotas=[quota()])
    catalog=handoff()
    catalog.checks[0].action_budget=7
    with pytest.raises(HandoffError):
        consume_product_handoff(candidate=catalog, quotas=[quota()])
