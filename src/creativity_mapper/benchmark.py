"""Creativity benchmark: an LLM judge scores a finished run on three criteria.

* Semantic Distance: how bold the jump between the two domains is. Judged once per
  run, on the phenomenon and the mapping.
* Metaphorical Density: how deeply the concept's mechanics are built into a piece.
* Freedom from Cliche: how well a piece avoids stock AI phrasing, corporate buzzwords
  and predictable story shapes. Both are judged for each creative report.

The Creativity Index (out of 30) is Semantic Distance plus the mean Metaphorical
Density plus the mean Freedom from Cliche across the creative reports.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from crewai import LLM

from creativity_mapper.observability import format_elapsed, logger
from creativity_mapper.report import CREATIVE_REPORTS, REPORT_TITLES, scoped_reports

MAX_REPORT_CHARS = 12_000
JUDGE_ATTEMPTS = 3
RETRY_DELAYS = (3, 8)  # seconds to wait before the 2nd and 3rd attempts
MAX_CONSECUTIVE_FAILURES = 2
SECTION_HEADING = "## Creativity benchmark"

INTRO = """You are an expert evaluator in computational creativity and divergent thinking.
You score cross-domain creative work strictly and consistently. Use the whole 1-10
scale. Typical language-model output deserves 3 to 6; give 8 or more only with clear
evidence of real surprise, and 10 only for work that is exceptional and rare. Back every
score with specific evidence from the text. Only quote words and phrases that actually
appear in the piece; examples given in these instructions are not evidence. Section
headings and field labels (for example "Logline", "MVP Features", "Image Prompt") come
from a fixed template and are never to be judged or cited."""

SEMANTIC_DISTANCE_PROMPT = INTRO + """

Primary Domain: {primary}
Target Domain: {target}

Score SEMANTIC DISTANCE (1-10): how bold and unexpected is the conceptual jump from the
Primary Domain to the Target Domain in the mapping below? Consider both how far apart the
domains are and whether the chosen phenomenon and mapping exploit that distance in a
non-obvious way. A distant pair mapped through an obvious, well-worn analogy scores low.
  1-3  cliche or obvious analogy, the kind everyone reaches for first
  4-6  reasonable and clear, but the connection is predictable
  7-9  surprising connection that still holds together structurally
  10   mind-bending and novel, yet the structure survives scrutiny

=== PHENOMENON ===
{phenomenon}

=== MAPPING ===
{mapping}

Reply with only a JSON object, no other text:
{{"semantic_distance": {{"score": <integer 1-10>, "evidence": "<one or two sentences>"}}}}"""

REPORT_PROMPT = INTRO + """

You are scoring one creative piece ("{title}") written from a concept in the domain of
{target}. The concept's mechanics are described in the brief.

Score two criteria (1-10 each):

METAPHORICAL DENSITY: how deeply and inventively are the concept's core mechanics built
into the piece, rather than name-dropped?
  1-3  mechanics barely present, or only decorative theming
  4-6  present and recognizable, but mostly surface dressing
  7-9  the mechanics drive the plot, rules, structure or product behavior in specific,
       non-obvious ways
  10   the piece could not exist without the mechanics, and it extends them surprisingly

FREEDOM FROM CLICHE: did the piece avoid standard AI tropes, corporate buzzwords and
predictable structures? Penalize stock phrasing ("tapestry", "delve", "symphony of",
"a testament to"), corporate buzzwords ("synergy", "leverage", "seamless", "empower",
"AI-powered", "dashboard"), predictable shapes (neon-soaked dystopia, chosen one, "in a
world where", the insider whistleblower, the AI-was-behind-it twist, a rogue
investigator), and generic invented names (Dr. Elena Vance, Kaelen Voss and the like).
  1-3  built mostly from stock tropes and phrasing
  4-6  some fresh moments inside a familiar template
  7-9  distinctive voice and structure, with only incidental cliches
  10   original throughout

=== BRIEF ===
{brief}

=== PIECE ===
{piece}

Reply with only a JSON object, no other text:
{{"metaphorical_density": {{"score": <integer 1-10>, "evidence": "<one or two sentences>"}},
 "freedom_from_cliche": {{"score": <integer 1-10>, "evidence": "<one or two sentences>",
 "cliches_found": ["<short quoted examples, or an empty list>"]}}}}"""


@dataclass
class Criterion:
    score: int | None
    evidence: str = ""
    cliches: list[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    primary: str
    target: str
    judge_model: str
    semantic_distance: Criterion
    reports: dict[str, dict[str, Criterion]]
    index: float | None = None

    @property
    def partial(self) -> bool:
        """True when fewer creative reports were scored than a full run produces."""
        return len(self.reports) < len(CREATIVE_REPORTS)

    def scope_note(self) -> str:
        titles = ", ".join(REPORT_TITLES[n] for n in self.reports)
        return (
            f"Partial run: scored {len(self.reports)} of {len(CREATIVE_REPORTS)} creative "
            f"reports ({titles}). Semantic distance is judged as usual, but the other two "
            f"scores rest on {'a single piece' if len(self.reports) == 1 else 'few pieces'}, "
            f"so this index is noisier and not comparable with full-run indexes."
        )

    def mean(self, criterion: str) -> float | None:
        scores = [r[criterion].score for r in self.reports.values() if r[criterion].score]
        return round(sum(scores) / len(scores), 1) if scores else None

    def compute_index(self) -> None:
        parts = [
            self.semantic_distance.score,
            self.mean("metaphorical_density"),
            self.mean("freedom_from_cliche"),
        ]
        self.index = None if None in parts else round(sum(parts), 1)


def parse_judgement(reply: str) -> dict | None:
    """Pull the JSON object out of a judge reply, tolerating code fences and chatter."""
    match = re.search(r"\{.*\}", str(reply), re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def to_criterion(raw: object) -> Criterion:
    """Turn one criterion's JSON into a Criterion with a score clamped to 1-10."""
    if not isinstance(raw, dict):
        return Criterion(None, "judge reply was missing this criterion")
    try:
        score = max(1, min(10, round(float(raw["score"]))))
    except (KeyError, TypeError, ValueError):
        return Criterion(None, "judge gave no usable score")
    cliches = raw.get("cliches_found") or []
    return Criterion(
        score,
        str(raw.get("evidence", "")).strip(),
        [str(c) for c in cliches][:8] if isinstance(cliches, list) else [],
    )


def ground_cliches(cliches: list[str], piece: str) -> list[str]:
    """Keep only the quoted cliches that really occur in the piece (case-insensitive).

    The judge sometimes echoes the example words from its own instructions, so every
    quote is checked against the text.
    """
    text = piece.lower()
    kept = [c for c in cliches if c.strip().lower() and c.strip().lower() in text]
    if len(kept) < len(cliches):
        logger.info("dropped %d cliche quote(s) not found in the text", len(cliches) - len(kept))
    return kept


class JudgeUnavailable(RuntimeError):
    """The judge model could not be reached, even after retries."""


def ask_judge(llm: LLM, prompt: str, label: str, sleep=None) -> dict | None:
    """Call the judge and return its parsed JSON reply.

    Unlike agent calls, a direct `llm.call` has no retry layer, so network errors and
    unparseable replies are retried here. Raises JudgeUnavailable if the model cannot
    be reached; returns None if it answered but never with usable JSON.
    """
    last_error: Exception | None = None
    answered = False
    for attempt in range(1, JUDGE_ATTEMPTS + 1):
        try:
            reply = llm.call(prompt)
        except Exception as e:  # network, timeout, quota: all worth another try
            last_error = e
            logger.warning("judge call for %s failed (attempt %d): %s", label, attempt, e)
        else:
            answered = True
            data = parse_judgement(reply)
            if data is not None:
                return data
            logger.warning("judge reply for %s was not valid JSON (attempt %d)", label, attempt)
        if attempt < JUDGE_ATTEMPTS:
            (sleep or time.sleep)(RETRY_DELAYS[attempt - 1])
    if not answered:
        raise JudgeUnavailable(str(last_error)) from last_error
    return None


def read_report(run_dir: Path, name: str) -> str:
    path = run_dir / name
    if not path.exists():
        return ""
    return re.sub(r"^> .*\n", "", path.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE)[
        :MAX_REPORT_CHARS
    ]


def read_domains(run_dir: Path) -> tuple[str, str]:
    """Recover the two domains from the heading of a run's README.md ("# A → B")."""
    readme = run_dir / "README.md"
    if readme.exists():
        match = re.search(r"^# (.+?) → (.+)$", readme.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    raise ValueError(f"Cannot find the domains in {readme}; expected a '# A → B' heading.")


def run_benchmark(run_dir: Path, primary: str, target: str, judge: LLM) -> BenchmarkResult:
    """Score a finished run with the judge model and return the results."""
    # Runs from before the target-domain brief existed fall back to the mapping.
    brief = read_report(run_dir, "03b_target_brief.md") or read_report(run_dir, "02_mapping.md")

    logger.info("benchmark started (judge %s)", judge.model)
    failures = 0

    def judged(prompt: str, label: str) -> dict | None:
        """ask_judge, but one unreachable call leaves an n/a score instead of losing the run."""
        nonlocal failures
        try:
            data = ask_judge(judge, prompt, label)
        except JudgeUnavailable:
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                raise
            print(f"  could not reach the judge for {label}; scored as n/a")
            return None
        failures = 0
        return data

    print("Judging semantic distance...")
    data = judged(
        SEMANTIC_DISTANCE_PROMPT.format(
            primary=primary,
            target=target,
            phenomenon=read_report(run_dir, "01_phenomenon.md"),
            mapping=read_report(run_dir, "02_mapping.md"),
        ),
        "semantic distance",
    )
    distance = to_criterion((data or {}).get("semantic_distance"))

    reports: dict[str, dict[str, Criterion]] = {}
    # A partial run records which agents ran in its README; otherwise score what exists.
    scoped = scoped_reports(run_dir)
    names = [n for n in (scoped if scoped is not None else CREATIVE_REPORTS) if (run_dir / n).exists()]
    for i, name in enumerate(names, 1):
        print(f"Judging [{i}/{len(names)}] {REPORT_TITLES[name]}...")
        piece = read_report(run_dir, name)
        data = judged(
            REPORT_PROMPT.format(
                title=REPORT_TITLES[name], target=target, brief=brief, piece=piece
            ),
            name,
        ) or {}
        cliche_freedom = to_criterion(data.get("freedom_from_cliche"))
        cliche_freedom.cliches = ground_cliches(cliche_freedom.cliches, piece)
        reports[name] = {
            "metaphorical_density": to_criterion(data.get("metaphorical_density")),
            "freedom_from_cliche": cliche_freedom,
        }
        logger.info(
            "judged %s: density %s, cliche-freedom %s",
            name,
            reports[name]["metaphorical_density"].score,
            reports[name]["freedom_from_cliche"].score,
        )

    result = BenchmarkResult(primary, target, str(judge.model), distance, reports)
    result.compute_index()
    logger.info("benchmark finished: creativity index %s/30", result.index)
    return result


def fmt(value: float | int | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def render_markdown(result: BenchmarkResult, usage_line: str = "") -> str:
    """The full benchmark report as Markdown."""
    lines = [
        f"# Creativity Benchmark: {result.primary} → {result.target}",
        "",
        f"**Creativity Index: {fmt(result.index)} / 30**",
        "",
        *([f"> **{result.scope_note()}**", ""] if result.partial else []),
        "| Criterion | Score | Basis |",
        "| --- | ---: | --- |",
        f"| Semantic Distance | {fmt(result.semantic_distance.score)} | the phenomenon and mapping |",
        f"| Metaphorical Density | {fmt(result.mean('metaphorical_density'))} | mean over {len(result.reports)} creative reports |",
        f"| Freedom from Cliché | {fmt(result.mean('freedom_from_cliche'))} | mean over {len(result.reports)} creative reports |",
        "",
        f"Semantic Distance: {result.semantic_distance.evidence}",
        "",
        "## By format",
        "",
        "| Report | Metaphorical Density | Freedom from Cliché | Sum (of 20) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, scores in result.reports.items():
        md, cf = scores["metaphorical_density"].score, scores["freedom_from_cliche"].score
        total = md + cf if md and cf else None
        lines.append(f"| {REPORT_TITLES[name]} | {fmt(md)} | {fmt(cf)} | {fmt(total)} |")

    lines += ["", "## Judge's notes", ""]
    for name, scores in result.reports.items():
        md, cf = scores["metaphorical_density"], scores["freedom_from_cliche"]
        lines += [
            f"### {REPORT_TITLES[name]}",
            f"- **Metaphorical Density ({fmt(md.score)}):** {md.evidence}",
            f"- **Freedom from Cliché ({fmt(cf.score)}):** {cf.evidence}",
        ]
        if cf.cliches:
            lines.append("- **Clichés found:** " + "; ".join(f"“{c}”" for c in cf.cliches))
        lines.append("")

    lines += [
        "## About these scores",
        "",
        f"Judge model: `{result.judge_model}`. {usage_line}".strip(),
        "",
        "An LLM judge is noisy and tends to favor its own style, so compare scores only "
        "between runs scored by the same judge model, and treat differences of a point or "
        "so as noise.",
        "",
    ]
    return "\n".join(lines)


def save_benchmark(run_dir: Path, result: BenchmarkResult, usage_line: str = "") -> Path:
    """Write creativity_benchmark.md and .json, and add a summary to the run's README.md."""
    md_path = run_dir / "creativity_benchmark.md"
    md_path.write_text(render_markdown(result, usage_line), encoding="utf-8")

    payload = {
        "primary": result.primary,
        "target": result.target,
        "judge_model": result.judge_model,
        "creativity_index": result.index,
        "partial": result.partial,
        "reports_scored": len(result.reports),
        "semantic_distance": result.semantic_distance.score,
        "metaphorical_density": result.mean("metaphorical_density"),
        "freedom_from_cliche": result.mean("freedom_from_cliche"),
        "reports": {
            name: {k: v.score for k, v in scores.items()}
            for name, scores in result.reports.items()
        },
    }
    (run_dir / "creativity_benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    readme = run_dir / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        text = text.split(SECTION_HEADING)[0].rstrip() + "\n"
        text += (
            f"\n{SECTION_HEADING}\n\n"
            f"**Creativity Index: {fmt(result.index)} / 30** "
            f"(semantic distance {fmt(result.semantic_distance.score)}, "
            f"metaphorical density {fmt(result.mean('metaphorical_density'))}, "
            f"freedom from cliché {fmt(result.mean('freedom_from_cliche'))}). "
            f"Details: [creativity_benchmark.md](creativity_benchmark.md).\n"
        )
        if result.partial:
            text += f"\n_{result.scope_note()}_\n"
        readme.write_text(text, encoding="utf-8")
    return md_path


def benchmark_run(run_dir: Path, primary: str, target: str, judge: LLM) -> BenchmarkResult:
    """Score a run, save the results, and log the judge's token cost."""
    import time

    started = time.monotonic()
    before = judge.get_token_usage_summary().model_copy()
    result = run_benchmark(run_dir, primary, target, judge)
    used = judge.get_token_usage_summary().model_copy().delta_since(before)
    usage_line = (
        f"Judging used {used.prompt_tokens:,} input and {used.completion_tokens:,} output "
        f"tokens in {format_elapsed(time.monotonic() - started)}."
    )
    save_benchmark(run_dir, result, usage_line)
    return result
