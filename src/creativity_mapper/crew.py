import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from crewai import LLM, Agent, Crew, Process, Task
from crewai.tasks.task_output import TaskOutput
from crewai.types.usage_metrics import UsageMetrics

from creativity_mapper.agents import (
    analogical_mapper,
    analytical_critic,
    comic_scripter,
    concept_distiller,
    found_document_storyteller,
    game_designer,
    lyricist,
    musical_satirist,
    narrative_designer,
    phenomenon_explorer,
    podcast_scriptwriter,
    poet,
    product_builder,
)
from creativity_mapper.observability import Heartbeat, format_elapsed, logger
from creativity_mapper.report import count_domain_mentions, finalize_run
from creativity_mapper.tasks import (
    compile_found_documents,
    critique_mapping,
    design_game,
    distill_brief,
    explore_phenomenon,
    map_to_target,
    pitch_narratives,
    pitch_products,
    write_comic,
    write_lyrics,
    write_musical,
    write_podcast,
    write_poems,
)


BASE_LABELS = [
    "Exploring phenomenon",
    "Mapping to target",
    "Critiquing",
    "Distilling target-domain brief",
]


@dataclass(frozen=True)
class CreativeStep:
    """One creative agent and the report it writes. All of them read only the brief."""

    name: str  # the agent's display name, e.g. "Poet"
    label: str  # progress label
    report: str  # output file
    agent: Callable[[LLM], Agent]
    task: Callable[[Agent, Path, Task], Task]
    aliases: tuple[str, ...] = ()

    @property
    def number(self) -> str:
        return self.report[:2]

    def ids(self) -> set[str]:
        return {normalize_id(x) for x in (self.name, self.number, *self.aliases)}


def normalize_id(text: str) -> str:
    """Lower-case and drop everything but letters and digits: "Found-Document Storyteller"
    and "founddocumentstoryteller" are the same ID."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


CREATIVE_STEPS = [
    CreativeStep("Narrative Designer", "Writing narratives", "04_narratives.md", narrative_designer, pitch_narratives, ("narratives", "narrative")),
    CreativeStep("Product Builder", "Designing products", "05_products.md", product_builder, pitch_products, ("products", "product")),
    CreativeStep("Poet", "Writing poems", "06_poems.md", poet, write_poems, ("poems", "poem")),
    CreativeStep("Lyricist", "Writing lyrics", "07_lyrics.md", lyricist, write_lyrics, ("lyrics",)),
    CreativeStep("Comic Scripter", "Scripting comic", "08_comic.md", comic_scripter, write_comic, ("comic",)),
    CreativeStep("Podcast Scriptwriter", "Writing podcast", "09_podcast.md", podcast_scriptwriter, write_podcast, ("podcast",)),
    CreativeStep("Satirical Musical Writer", "Writing musical", "10_musical.md", musical_satirist, write_musical, ("musical",)),
    CreativeStep("Game Designer", "Designing game", "11_game.md", game_designer, design_game, ("game",)),
    CreativeStep("Found-Document Storyteller", "Compiling found documents", "12_found_documents.md", found_document_storyteller, compile_found_documents, ("documents", "founddocuments")),
]


def agent_ids() -> list[str]:
    """Display names of the agents that can be selected with --only."""
    return [step.name for step in CREATIVE_STEPS]


def resolve_agents(requested: list[str]) -> list[CreativeStep]:
    """Map names or IDs given with --only to creative steps, in pipeline order.

    Matching ignores case and punctuation and accepts the agent's name ("Poet"), a short
    alias ("poems") or the report number ("06"). Raises ValueError for anything unknown.
    """
    chosen: dict[str, CreativeStep] = {}
    for text in requested:
        key = normalize_id(text)
        step = next((s for s in CREATIVE_STEPS if key in s.ids()), None)
        if step is None:
            raise ValueError(f"unknown agent {text!r}; choose from: {', '.join(agent_ids())}")
        chosen[step.name] = step
    return [s for s in CREATIVE_STEPS if s.name in chosen]


class RunTracker:
    """Prints progress, logs timings and records per-step token usage.

    Tasks run one at a time and every agent shares one LLM, so a step's usage is
    the growth of the LLM's lifetime counters since the previous step finished.
    """

    def __init__(self, llm: LLM, labels: list[str]):
        self._llm = llm
        self.labels = labels
        self._last = llm.get_token_usage_summary().model_copy()
        self._step_started = time.monotonic()
        self.usage: list[tuple[str, UsageMetrics]] = []

    @property
    def current(self) -> tuple[str, float]:
        """Label of the step now running and how long it has been running."""
        index = min(len(self.usage), len(self.labels) - 1)
        return self.labels[index], time.monotonic() - self._step_started

    def started(self) -> None:
        print(f"[0/{len(self.labels)}] Starting: {self.labels[0]}...")
        logger.info("step 1/%d '%s' started", len(self.labels), self.labels[0])

    def __call__(self, _output: TaskOutput) -> None:
        now = self._llm.get_token_usage_summary().model_copy()
        label, elapsed = self.current
        delta = now.delta_since(self._last)
        self.usage.append((label, delta))
        self._last = now
        self._step_started = time.monotonic()

        done, total = len(self.usage), len(self.labels)
        print(f"[{done}/{total}] {label} complete ({format_elapsed(elapsed)})")
        logger.info(
            "step %d/%d '%s' finished in %s (input %d, completion %d, reasoning %d, requests %d)",
            done, total, label, format_elapsed(elapsed),
            delta.prompt_tokens, delta.completion_tokens, delta.reasoning_tokens,
            delta.successful_requests,
        )
        if done < total:
            logger.info("step %d/%d '%s' started", done + 1, total, self.labels[done])


def run_crew(
    primary: str,
    target: str,
    run_dir: Path,
    llm: LLM,
    verbose: bool = False,
    only: list[CreativeStep] | None = None,
):
    """Run the analytical steps (1-3b), then the creative agents.

    `only` limits the creative agents to those given; the analytical steps always run
    because every creative agent depends on the brief they produce.
    """
    steps = only or CREATIVE_STEPS
    partial = len(steps) < len(CREATIVE_STEPS)
    labels = BASE_LABELS + [step.label for step in steps]

    explorer = phenomenon_explorer(llm)
    mapper = analogical_mapper(llm)
    critic = analytical_critic(llm)
    distiller = concept_distiller(llm)

    phenomenon = explore_phenomenon(explorer, run_dir)
    mapping = map_to_target(mapper, run_dir, phenomenon)
    critique = critique_mapping(critic, run_dir, mapping)
    brief = distill_brief(distiller, run_dir, mapping, critique, primary, target, llm)

    agents = [explorer, mapper, critic, distiller]
    tasks = [phenomenon, mapping, critique, brief]
    for step in steps:
        agent = step.agent(llm)
        agents.append(agent)
        tasks.append(step.task(agent, run_dir, brief))

    tracker = RunTracker(llm, labels)
    crew = Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=verbose,
        task_callback=tracker,
    )

    logger.info("creative agents: %s", ", ".join(step.name for step in steps))
    tracker.started()
    started = time.monotonic()
    try:
        with Heartbeat(lambda: tracker.current):
            result = crew.kickoff(
                inputs={"primary_domain": primary, "target_domain": target}
            )
    except Exception:
        label, elapsed = tracker.current
        step_no = len(tracker.usage) + 1
        logger.exception(
            "step %d/%d '%s' failed after %s", step_no, len(labels), label, format_elapsed(elapsed)
        )
        print(
            f"\nFailed during step {step_no}/{len(labels)} ('{label}') "
            f"after {format_elapsed(elapsed)}.",
            file=sys.stderr,
        )
        raise

    leaks = count_domain_mentions(run_dir, primary, [step.report for step in steps])
    logger.info("primary-domain term mentions per creative report: %s", leaks)
    print(
        f"Primary-domain term mentions in the {len(leaks)} creative "
        f"report{'s' if len(leaks) != 1 else ''}: "
        f"{sum(leaks.values())} (per-report counts in run.log)"
    )
    logger.info("run finished in %s", format_elapsed(time.monotonic() - started))
    finalize_run(
        run_dir,
        primary,
        target,
        usage=tracker.usage,
        partial=[step.name for step in steps] if partial else None,
    )
    return result
