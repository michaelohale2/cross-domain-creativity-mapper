from datetime import datetime

from crewai.types.usage_metrics import UsageMetrics

from creativity_mapper.report import scoped_reports, CREATIVE_REPORTS, count_domain_mentions, domain_pattern, add_header, clean_markdown, finalize_run, preserve_line_breaks, usage_table

WHEN = datetime(2026, 10, 25, 14, 30)


def test_strips_wrapping_fence():
    assert clean_markdown("```markdown\n# Title\n\nBody\n```") == "# Title\n\nBody\n"


def test_keeps_inner_code_blocks():
    text = "# T\n\n```py\nx = 1\n```\n\nmore"
    assert clean_markdown(text) == text + "\n"


def test_bold_field_lines_become_separate_paragraphs():
    raw = "## C\n**Genre:** Noir\n**Logline:** Rain.\n**Setting:** City\n\nplain"
    assert clean_markdown(raw) == "## C\n**Genre:** Noir\n\n**Logline:** Rain.\n\n**Setting:** City\n\nplain\n"


def test_bullet_fields_are_left_alone():
    raw = "- **Concept:** x\n- **Risk:** y"
    assert clean_markdown(raw) == raw + "\n"


def test_header_goes_under_title():
    out = add_header("# Title\n\n## Section\n", "Biology", "Politics", WHEN)
    assert out == "# Title\n\n> Biology → Politics · 2026-10-25 14:30\n\n## Section\n"


def test_header_without_title():
    out = add_header("Just text\n", "A", "B", WHEN)
    assert out.startswith("> A → B · 2026-10-25 14:30\n\nJust text")


def test_finalize_writes_index_for_existing_reports(tmp_path):
    (tmp_path / "01_phenomenon.md").write_text("# P\n\nx\n")
    (tmp_path / "03_critique.md").write_text("# C\n\ny\n")
    finalize_run(tmp_path, "Biology", "Politics", WHEN)
    index = (tmp_path / "README.md").read_text()
    assert "[Phenomenon](01_phenomenon.md)" in index
    assert "[Critique](03_critique.md)" in index
    assert "02_mapping.md" not in index
    assert "> Biology → Politics" in (tmp_path / "01_phenomenon.md").read_text()


def test_usage_table_separates_reasoning_and_totals():
    usage = [
        ("Exploring", UsageMetrics(prompt_tokens=100, completion_tokens=70, reasoning_tokens=20, total_tokens=170)),
        ("Mapping", UsageMetrics(prompt_tokens=1000, completion_tokens=500, reasoning_tokens=0, total_tokens=1500)),
    ]
    table = "\n".join(usage_table(usage))
    assert "| Exploring | 100 | 50 | 20 | 170 |" in table
    assert "| Mapping | 1,000 | 500 | 0 | 1,500 |" in table
    assert "| **Total** | **1,100** | **550** | **20** | **1,670** |" in table


def test_finalize_adds_usage_section(tmp_path):
    (tmp_path / "01_phenomenon.md").write_text("# P\n")
    usage = [("Exploring", UsageMetrics(prompt_tokens=1, completion_tokens=1, total_tokens=2))]
    finalize_run(tmp_path, "A", "B", WHEN, usage=usage)
    assert "## Token usage" in (tmp_path / "README.md").read_text()


def test_preserve_line_breaks_keeps_verse_lines_apart():
    raw = "## Poem 1: Rain\n*Haiku*\nline one\nline two\n\nline three"
    assert preserve_line_breaks(raw) == "## Poem 1: Rain\n*Haiku*  \nline one  \nline two\n\nline three"


def test_domain_pattern_matches_word_variants_only():
    pattern = domain_pattern("Geology")
    assert len(pattern.findall("Geology and geological strata, geologists")) == 3
    assert not pattern.findall("jazz and music")


def test_domain_pattern_handles_multiword_domains():
    pattern = domain_pattern("Quantum Physics")
    assert len(pattern.findall("quantum tunnelling and physical laws")) == 2


def test_count_domain_mentions_skips_missing_reports(tmp_path):
    (tmp_path / "05_products.md").write_text("Geology Geology jazz")
    counts = count_domain_mentions(tmp_path, "Geology", ["05_products.md", "06_poems.md"])
    assert counts == {"05_products.md": 2}


def test_creative_reports_start_after_the_brief():
    assert CREATIVE_REPORTS[0] == "04_narratives.md"
    assert CREATIVE_REPORTS[-1] == "13_pitch.md"
    assert len(CREATIVE_REPORTS) == 10


def test_partial_run_records_its_scope_in_the_readme(tmp_path):
    (tmp_path / "01_phenomenon.md").write_text("# P\n")
    (tmp_path / "06_poems.md").write_text("# Poems\n")
    finalize_run(tmp_path, "A", "B", WHEN, partial=["Poet"])
    readme = (tmp_path / "README.md").read_text()
    assert "**Partial run.** Only these creative agents ran: Poet." in readme
    assert scoped_reports(tmp_path) == ["06_poems.md"]


def test_full_run_has_no_scope(tmp_path):
    (tmp_path / "06_poems.md").write_text("# Poems\n")
    finalize_run(tmp_path, "A", "B", WHEN)
    assert scoped_reports(tmp_path) is None
    assert scoped_reports(tmp_path / "missing") is None
