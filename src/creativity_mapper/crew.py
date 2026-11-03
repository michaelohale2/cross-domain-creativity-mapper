import sys
import time
from pathlib import Path

from crewai import LLM, Crew, Process
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
from creativity_mapper.report import CREATIVE_REPORTS, count_domain_mentions, finalize_run
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


TASK_LABELS = [
    "Exploring phenomenon",
    "Mapping to target",
    "Critiquing",
    "Distilling target-domain brief",
    "Writing narratives",
    "Designing products",
    "Writing poems",
    "Writing lyrics",
    "Scripting comic",
    "Writing podcast",
    "Writing musical",
    "Designing game",
    "Compiling found documents",
]


class RunTracker:
    """Prints progress, logs timings and records per-step token usage.

    Tasks run one at a time and every agent shares one LLM, so a step's usage is
    the growth of the LLM's lifetime counters since the previous step finished.
    """

    def __init__(self, llm: LLM):
        self._llm = llm
        self._last = llm.get_token_usage_summary().model_copy()
        self._step_started = time.monotonic()
        self.usage: list[tuple[str, UsageMetrics]] = []

    @property
    def current(self) -> tuple[str, float]:
        """Label of the step now running and how long it has been running."""
        index = min(len(self.usage), len(TASK_LABELS) - 1)
        return TASK_LABELS[index], time.monotonic() - self._step_started

    def started(self) -> None:
        print(f"[0/{len(TASK_LABELS)}] Starting: {TASK_LABELS[0]}...")
        logger.info("step 1/%d '%s' started", len(TASK_LABELS), TASK_LABELS[0])

    def __call__(self, _output: TaskOutput) -> None:
        now = self._llm.get_token_usage_summary().model_copy()
        label, elapsed = self.current
        delta = now.delta_since(self._last)
        self.usage.append((label, delta))
        self._last = now
        self._step_started = time.monotonic()

        done, total = len(self.usage), len(TASK_LABELS)
        print(f"[{done}/{total}] {label} complete ({format_elapsed(elapsed)})")
        logger.info(
            "step %d/%d '%s' finished in %s (input %d, completion %d, reasoning %d, requests %d)",
            done, total, label, format_elapsed(elapsed),
            delta.prompt_tokens, delta.completion_tokens, delta.reasoning_tokens,
            delta.successful_requests,
        )
        if done < total:
            logger.info("step %d/%d '%s' started", done + 1, total, TASK_LABELS[done])


def run_crew(
    primary: str, target: str, run_dir: Path, llm: LLM, verbose: bool = False
):
    explorer = phenomenon_explorer(llm)
    mapper = analogical_mapper(llm)
    critic = analytical_critic(llm)
    distiller = concept_distiller(llm)
    designer = narrative_designer(llm)
    builder = product_builder(llm)
    poet_agent = poet(llm)
    songwriter = lyricist(llm)
    comic_writer = comic_scripter(llm)
    podcaster = podcast_scriptwriter(llm)
    satirist = musical_satirist(llm)
    game_agent = game_designer(llm)
    archivist = found_document_storyteller(llm)

    phenomenon = explore_phenomenon(explorer, run_dir)
    mapping = map_to_target(mapper, run_dir, phenomenon)
    critique = critique_mapping(critic, run_dir, mapping)
    brief = distill_brief(distiller, run_dir, mapping, critique, primary, target, llm)
    narratives = pitch_narratives(designer, run_dir, brief)
    products = pitch_products(builder, run_dir, brief)
    poems = write_poems(poet_agent, run_dir, brief)
    lyrics = write_lyrics(songwriter, run_dir, brief)
    comic = write_comic(comic_writer, run_dir, brief)
    podcast = write_podcast(podcaster, run_dir, brief)
    musical = write_musical(satirist, run_dir, brief)
    game = design_game(game_agent, run_dir, brief)
    documents = compile_found_documents(archivist, run_dir, brief)

    tracker = RunTracker(llm)
    crew = Crew(
        agents=[
            explorer, mapper, critic, distiller, designer, builder, poet_agent, songwriter,
            comic_writer, podcaster, satirist, game_agent, archivist,
        ],
        tasks=[
            phenomenon, mapping, critique, brief, narratives, products, poems, lyrics,
            comic, podcast, musical, game, documents,
        ],
        process=Process.sequential,
        verbose=verbose,
        task_callback=tracker,
    )

    tracker.started()
    started = time.monotonic()
    try:
        with Heartbeat(lambda: tracker.current):
            result = crew.kickoff(
                inputs={"primary_domain": primary, "target_domain": target}
            )
    except Exception:
        label, elapsed = tracker.current
        step = len(tracker.usage) + 1
        logger.exception(
            "step %d/%d '%s' failed after %s", step, len(TASK_LABELS), label, format_elapsed(elapsed)
        )
        print(
            f"\nFailed during step {step}/{len(TASK_LABELS)} ('{label}') "
            f"after {format_elapsed(elapsed)}.",
            file=sys.stderr,
        )
        raise

    leaks = count_domain_mentions(run_dir, primary, CREATIVE_REPORTS)
    logger.info("primary-domain term mentions per creative report: %s", leaks)
    print(
        f"Primary-domain term mentions in the {len(leaks)} creative reports: "
        f"{sum(leaks.values())} (per-report counts in run.log)"
    )
    logger.info("run finished in %s", format_elapsed(time.monotonic() - started))
    finalize_run(run_dir, primary, target, usage=tracker.usage)
    return result
