import pytest

from creativity_mapper.crew import CREATIVE_STEPS, agent_ids, resolve_agents


def names(requested):
    return [step.name for step in resolve_agents(requested)]


def test_matches_by_name_alias_and_report_number_ignoring_case_and_punctuation():
    assert names(["Poet"]) == ["Poet"]
    assert names(["poems"]) == ["Poet"]
    assert names(["06"]) == ["Poet"]
    assert names(["found-document storyteller"]) == ["Found-Document Storyteller"]
    assert names(["Satirical Musical Writer"]) == ["Satirical Musical Writer"]


def test_results_follow_pipeline_order_and_ignore_duplicates():
    assert names(["lyrics", "poet", "Poet"]) == ["Poet", "Lyricist"]


def test_unknown_agent_lists_the_valid_ones():
    with pytest.raises(ValueError) as error:
        resolve_agents(["Singer"])
    assert "Singer" in str(error.value)
    assert all(name in str(error.value) for name in agent_ids())


def test_every_creative_step_is_selectable_by_each_of_its_ids():
    for step in CREATIVE_STEPS:
        for identifier in (step.name, step.number, *step.aliases):
            assert names([identifier]) == [step.name]


def test_registry_matches_the_reports_the_benchmark_scores():
    from creativity_mapper.report import CREATIVE_REPORTS

    assert [s.report for s in CREATIVE_STEPS] == CREATIVE_REPORTS
