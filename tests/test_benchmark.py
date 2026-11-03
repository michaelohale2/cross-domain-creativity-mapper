import json

import pytest

from creativity_mapper.benchmark import (
    BenchmarkResult,
    Criterion,
    JudgeUnavailable,
    ask_judge,
    ground_cliches,
    parse_judgement,
    read_domains,
    render_markdown,
    run_benchmark,
    save_benchmark,
    to_criterion,
)


def make_result(md=(6, 8), cf=(4, 4), distance=7):
    reports = {
        "04_narratives.md": {
            "metaphorical_density": Criterion(md[0], "dense"),
            "freedom_from_cliche": Criterion(cf[0], "tropey", ["neon-soaked sprawl"]),
        },
        "05_products.md": {
            "metaphorical_density": Criterion(md[1], "ok"),
            "freedom_from_cliche": Criterion(cf[1], "buzzwords"),
        },
    }
    result = BenchmarkResult("Geology", "Jazz", "gemini/judge", Criterion(distance, "bold"), reports)
    result.compute_index()
    return result


def test_parse_plain_and_fenced_json():
    assert parse_judgement('{"a": 1}') == {"a": 1}
    assert parse_judgement('Sure!\n```json\n{"a": {"score": 5}}\n```\nDone') == {"a": {"score": 5}}


@pytest.mark.parametrize("bad", ["", "no json here", "{broken", "[1, 2]"])
def test_parse_rejects_unusable_replies(bad):
    assert parse_judgement(bad) is None


def test_scores_are_clamped_and_rounded():
    assert to_criterion({"score": 14}).score == 10
    assert to_criterion({"score": 0}).score == 1
    assert to_criterion({"score": "6.6", "evidence": " x "}) == Criterion(7, "x", [])


def test_missing_or_garbled_score_is_none():
    assert to_criterion(None).score is None
    assert to_criterion({"evidence": "no score"}).score is None
    assert to_criterion({"score": "high"}).score is None


def test_creativity_index_is_distance_plus_the_two_means():
    result = make_result(md=(6, 8), cf=(4, 4), distance=7)
    assert result.mean("metaphorical_density") == 7.0
    assert result.mean("freedom_from_cliche") == 4.0
    assert result.index == 18.0


def test_failed_scores_are_left_out_of_the_mean_and_missing_distance_voids_the_index():
    result = make_result()
    result.reports["05_products.md"]["metaphorical_density"] = Criterion(None, "failed")
    assert result.mean("metaphorical_density") == 6.0
    result.semantic_distance = Criterion(None, "failed")
    result.compute_index()
    assert result.index is None


def test_domains_are_read_from_the_run_readme(tmp_path):
    (tmp_path / "README.md").write_text("# Quantum Physics → Macroeconomics\n\nGenerated.\n")
    assert read_domains(tmp_path) == ("Quantum Physics", "Macroeconomics")
    with pytest.raises(ValueError):
        read_domains(tmp_path / "missing")


def test_markdown_report_lists_scores_and_cliches():
    text = render_markdown(make_result(), "Judging used 10 input tokens.")
    assert "**Creativity Index: 18 / 30**" in text
    assert "| Narrative Concepts | 6 | 4 | 10 |" in text
    assert "“neon-soaked sprawl”" in text
    assert "Judging used 10 input tokens." in text


def test_save_writes_files_and_replaces_the_readme_section(tmp_path):
    (tmp_path / "README.md").write_text("# Geology → Jazz\n\nGenerated.\n")
    save_benchmark(tmp_path, make_result(), "")
    save_benchmark(tmp_path, make_result(distance=9), "")  # re-scoring must not duplicate
    readme = (tmp_path / "README.md").read_text()
    assert readme.count("## Creativity benchmark") == 1
    assert "20 / 30" in readme
    data = json.loads((tmp_path / "creativity_benchmark.json").read_text())
    assert data["creativity_index"] == 20.0
    assert data["reports"]["05_products.md"] == {"metaphorical_density": 8, "freedom_from_cliche": 4}
    assert (tmp_path / "creativity_benchmark.md").exists()


def test_cliche_quotes_must_appear_in_the_piece():
    piece = "A real-time Dashboard for the board. Synergy is promised."
    quotes = ["dashboard", "Real-Time", "seamless", "ecosystem", "  "]
    assert ground_cliches(quotes, piece) == ["dashboard", "Real-Time"]


class FakeJudge:
    """Stands in for an LLM: replays a script of replies or exceptions."""

    model = "fake/judge"

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def call(self, _prompt):
        self.calls += 1
        item = self.script.pop(0) if self.script else '{"a": 1}'
        if isinstance(item, Exception):
            raise item
        return item


NO_WAIT = lambda _seconds: None  # noqa: E731


def test_judge_retries_network_errors_then_succeeds():
    judge = FakeJudge([OSError("dns"), OSError("dns"), '{"ok": 1}'])
    assert ask_judge(judge, "p", "x", sleep=NO_WAIT) == {"ok": 1}
    assert judge.calls == 3


def test_unreachable_judge_raises_after_all_attempts():
    judge = FakeJudge([OSError("dns")] * 3)
    with pytest.raises(JudgeUnavailable):
        ask_judge(judge, "p", "x", sleep=NO_WAIT)
    assert judge.calls == 3


def test_judge_that_answers_without_json_gives_none_not_an_error():
    judge = FakeJudge(["sorry, no"] * 3)
    assert ask_judge(judge, "p", "x", sleep=NO_WAIT) is None


def make_run_dir(tmp_path):
    for name in ("01_phenomenon.md", "02_mapping.md", "03b_target_brief.md", "04_narratives.md", "05_products.md", "06_poems.md"):
        (tmp_path / name).write_text(f"# {name}\n\ntext\n")
    return tmp_path


GOOD_REPORT = (
    '{"metaphorical_density": {"score": 6, "evidence": "e"},'
    ' "freedom_from_cliche": {"score": 5, "evidence": "e", "cliches_found": []}}'
)


def test_one_unreachable_report_becomes_na_and_scoring_continues(tmp_path, monkeypatch):
    monkeypatch.setattr("creativity_mapper.benchmark.time.sleep", lambda _s: None)
    run_dir = make_run_dir(tmp_path)
    # distance ok; narratives unreachable (3 failed attempts); products and poems ok
    script = ['{"semantic_distance": {"score": 7, "evidence": "e"}}'] + [OSError("x")] * 3 + [GOOD_REPORT] * 2
    result = run_benchmark(run_dir, "A", "B", FakeJudge(script))
    assert result.reports["04_narratives.md"]["metaphorical_density"].score is None
    assert result.reports["05_products.md"]["metaphorical_density"].score == 6
    assert result.index == 7 + 6 + 5


def test_scoring_stops_when_the_judge_stays_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr("creativity_mapper.benchmark.time.sleep", lambda _s: None)
    run_dir = make_run_dir(tmp_path)
    judge = FakeJudge([OSError("dns")] * 100)
    with pytest.raises(JudgeUnavailable):
        run_benchmark(run_dir, "A", "B", judge)
    assert judge.calls == 6  # two calls x three attempts, then it gives up


def test_partial_run_scores_only_the_reports_named_in_its_readme(tmp_path, monkeypatch):
    monkeypatch.setattr("creativity_mapper.benchmark.time.sleep", lambda _s: None)
    run_dir = make_run_dir(tmp_path)  # has 04, 05 and 06 on disk
    (run_dir / "README.md").write_text(
        "# A → B\n\n<!-- creative-reports: 06_poems.md -->\n"
    )
    script = ['{"semantic_distance": {"score": 7, "evidence": "e"}}', GOOD_REPORT]
    judge = FakeJudge(script)
    result = run_benchmark(run_dir, "A", "B", judge)
    assert list(result.reports) == ["06_poems.md"]
    assert judge.calls == 2
    assert result.partial


def test_partial_runs_are_flagged_in_every_output(tmp_path):
    result = make_result()
    assert result.partial
    assert "Partial run: scored 2 of 9" in render_markdown(result)
    (tmp_path / "README.md").write_text("# A → B\n")
    save_benchmark(tmp_path, result)
    assert "not comparable with full-run indexes" in (tmp_path / "README.md").read_text()
    data = json.loads((tmp_path / "creativity_benchmark.json").read_text())
    assert data["partial"] is True and data["reports_scored"] == 2
