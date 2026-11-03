import re
from datetime import datetime
from pathlib import Path

from crewai.types.usage_metrics import UsageMetrics

REPORT_TITLES = {
    "01_phenomenon.md": "Phenomenon",
    "02_mapping.md": "Analogical Mapping",
    "03_critique.md": "Critique",
    "03b_target_brief.md": "Target-Domain Brief",
    "04_narratives.md": "Narrative Concepts",
    "05_products.md": "Product Concepts",
    "06_poems.md": "Poems",
    "07_lyrics.md": "Song Lyrics",
    "08_comic.md": "Comic Panel Prompts",
    "09_podcast.md": "Podcast Script",
    "10_musical.md": "Satirical Musical",
    "11_game.md": "Game Design",
    "12_found_documents.md": "Found Documents",
}

# Reports meant to live in the target domain only (everything after the brief).
CREATIVE_REPORTS = [name for name in REPORT_TITLES if name[:2].isdigit() and int(name[:2]) >= 4]

_WRAPPING_FENCE = re.compile(r"\A\s*```[a-zA-Z]*\n(.*?)\n```\s*\Z", re.DOTALL)


# Consecutive "**Field:** value" lines render as one paragraph unless a blank line separates them.
_BOLD_LINE_RUN = re.compile(r"^(\*\*.+)\n(?=\*\*)", re.MULTILINE)


def clean_markdown(raw: str) -> str:
    """Strip a wrapping code fence and separate runs of bold field lines into paragraphs."""
    match = _WRAPPING_FENCE.match(raw)
    text = (match.group(1) if match else raw).strip()
    return _BOLD_LINE_RUN.sub(r"\1\n\n", text) + "\n"


def preserve_line_breaks(text: str) -> str:
    """End each verse line with a hard break so Markdown doesn't merge lines into one paragraph."""
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        following = lines[i + 1] if i + 1 < len(lines) else ""
        if line.strip() and following.strip() and not line.startswith("#") and not following.startswith("#"):
            line = line.rstrip() + "  "
        out.append(line)
    return "\n".join(out)


def add_header(text: str, primary: str, target: str, when: datetime) -> str:
    """Insert a one-line context blockquote under the first H1 (or at the top)."""
    line = f"> {primary} → {target} · {when:%Y-%m-%d %H:%M}\n"
    head, sep, rest = text.partition("\n")
    if head.startswith("# "):
        return f"{head}\n\n{line}\n{rest.lstrip(chr(10))}"
    return f"{line}\n{text}"


def usage_table(usage: list[tuple[str, UsageMetrics]]) -> list[str]:
    """Markdown table of token usage per step, with a total row.

    CrewAI's completion count includes reasoning tokens for Gemini, so output is
    shown net of reasoning to keep input + output + reasoning equal to the total.
    """
    rows = ["| Step | Input | Output | Reasoning | Total |", "| --- | ---: | ---: | ---: | ---: |"]
    totals = [0, 0, 0, 0]
    for label, m in usage:
        output = max(0, m.completion_tokens - m.reasoning_tokens)
        values = [m.prompt_tokens, output, m.reasoning_tokens, m.total_tokens]
        totals = [t + v for t, v in zip(totals, values)]
        rows.append(f"| {label} | " + " | ".join(f"{v:,}" for v in values) + " |")
    rows.append("| **Total** | " + " | ".join(f"**{v:,}**" for v in totals) + " |")
    return rows


def finalize_run(
    run_dir: Path,
    primary: str,
    target: str,
    when: datetime | None = None,
    usage: list[tuple[str, UsageMetrics]] | None = None,
) -> None:
    """Add context headers to each report and write a README.md index."""
    when = when or datetime.now()
    found = []
    for name, title in REPORT_TITLES.items():
        path = run_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        path.write_text(add_header(text, primary, target, when), encoding="utf-8")
        found.append((name, title))

    index = [f"# {primary} → {target}", "", f"Generated {when:%Y-%m-%d %H:%M}.", ""]
    index += [f"- [{title}]({name})" for name, title in found]
    if usage:
        index += ["", "## Token usage", ""] + usage_table(usage)
    (run_dir / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")


def domain_pattern(domain: str) -> re.Pattern[str]:
    """Rough matcher for a domain's vocabulary: the stem of each word of 4+ letters.

    "Geology" matches geology and geological; "Quantum Physics" matches quantum and
    physics. It is an indicator for spotting leakage, not an exact test.
    """
    stems = [
        re.escape(word[: max(4, len(word) - 2)])
        for word in re.findall(r"\w+", domain.lower())
        if len(word) >= 4
    ]
    return re.compile(r"\b(?:" + "|".join(stems) + ")", re.IGNORECASE) if stems else re.compile(r"(?!)")


def count_domain_mentions(run_dir: Path, domain: str, names: list[str]) -> dict[str, int]:
    """Count mentions of `domain`'s vocabulary in each named report that exists."""
    pattern = domain_pattern(domain)
    counts = {}
    for name in names:
        path = run_dir / name
        if path.exists():
            counts[name] = len(pattern.findall(path.read_text(encoding="utf-8")))
    return counts
