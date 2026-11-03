import argparse
import sys
import warnings
from pathlib import Path

from creativity_mapper.benchmark import benchmark_run, read_domains
from creativity_mapper.config import get_judge_llm, get_llm
from creativity_mapper.crew import agent_ids, resolve_agents, run_crew
from creativity_mapper.observability import logger, setup_run_logging
from creativity_mapper.paths import create_run_dir, sanitize_domain


def prompt_domain(label: str, example: str) -> str:
    """Ask until the user enters something that can become a folder name."""
    while True:
        value = input(f"{label} (e.g., {example}): ").strip()
        try:
            sanitize_domain(value)
        except ValueError:
            print("Please enter a domain containing at least one letter or digit.")
            continue
        return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="creativity-mapper",
        description="Map an unusual phenomenon from one domain onto another using a CrewAI pipeline.",
    )
    parser.add_argument("primary", nargs="?", help="Primary domain (prompted for if omitted)")
    parser.add_argument("target", nargs="?", help="Target domain (prompted for if omitted)")
    parser.add_argument(
        "--only", metavar="AGENT", action="append",
        help="Run only this creative agent after the analytical steps (1-3b), e.g. --only Poet. "
        "May be repeated. Agents: " + ", ".join(agent_ids()),
    )
    parser.add_argument(
        "-b", "--benchmark", action="store_true",
        help="After the run, score its creativity with a judge model (set JUDGE_MODEL in .env)",
    )
    parser.add_argument(
        "--score-run", metavar="RUN_DIR", type=Path,
        help="Only score an existing run folder (no generation) and exit",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full agent output while running")
    args = parser.parse_args(argv)
    if args.score_run is not None:
        if args.primary is not None or args.benchmark or args.only:
            parser.error("--score-run scores an existing run on its own; drop the domains, --benchmark and --only")
        if not args.score_run.is_dir():
            parser.error(f"{args.score_run} is not a run folder")
        return args
    if args.only:
        try:
            args.only_steps = resolve_agents(args.only)
        except ValueError as e:
            parser.error(str(e))
    else:
        args.only_steps = None
    if args.primary is not None and args.target is None:
        parser.error("provide both primary and target domains, or neither")
    for value in (args.primary, args.target):
        if value is not None:
            try:
                sanitize_domain(value)
            except ValueError as e:
                parser.error(str(e))
    return args


def short_error(e: Exception, limit: int = 300) -> str:
    text = " ".join(str(e).split())
    if "API key not valid" in text or "API_KEY_INVALID" in text:
        return "Gemini rejected GEMINI_API_KEY. Check the key in your .env file."
    if any(m in text for m in ("nodename nor servname", "Name or service not known", "Temporary failure in name resolution")):
        return "Could not reach the Gemini API (DNS lookup failed). Check your network or VPN and try again."
    return text if len(text) <= limit else text[:limit] + "..."


def score(run_dir: Path, primary: str, target: str) -> None:
    """Run the creativity benchmark on a finished run and print the headline."""
    result = benchmark_run(run_dir, primary, target, get_judge_llm())
    print(
        f"Creativity Index: {result.index if result.index is not None else 'n/a'} / 30 "
        f"(judge {result.judge_model}). Details: {run_dir / 'creativity_benchmark.md'}"
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.verbose:
        warnings.filterwarnings("ignore")

    if args.score_run is not None:
        run_dir = args.score_run.resolve()
        try:
            setup_run_logging(run_dir, verbose=args.verbose)
            score(run_dir, *read_domains(run_dir))
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            raise SystemExit(130)
        except (ValueError, OSError) as e:
            raise SystemExit(f"Cannot score {run_dir}: {e}")
        except Exception as e:
            logger.error("scoring failed: %s", e)
            raise SystemExit(f"Scoring failed ({type(e).__name__}): {short_error(e)}")
        return

    llm = get_llm()  # fail fast on a missing API key, before asking for input

    try:
        primary = args.primary or prompt_domain("Primary Domain", "Biology, Quantum Physics")
        target = args.target or prompt_domain("Target Domain", "Politics, Macroeconomics")

        run_dir = create_run_dir(primary, target)
        print(f"Results will be saved to: {run_dir}")
        log_path = setup_run_logging(run_dir, verbose=args.verbose)
        print(f"Log file: {log_path}")
        logger.info("run started: %s -> %s (model %s)", primary, target, llm.model)

        run_crew(primary, target, run_dir, llm, verbose=args.verbose, only=args.only_steps)
    except (KeyboardInterrupt, EOFError):
        logger.warning("run cancelled by user")
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as e:
        logger.error("run failed: %s", e)
        print(f"\nRun failed ({type(e).__name__}): {short_error(e)}", file=sys.stderr)
        print("Reports finished before the failure are kept in the run folder; details are in run.log.", file=sys.stderr)
        raise SystemExit(1)

    print(f"Done. Reports written to: {run_dir}")

    if args.benchmark:
        try:
            score(run_dir, primary, target)
        except KeyboardInterrupt:
            raise SystemExit(130)
        except Exception as e:
            logger.error("scoring failed: %s", e)
            raise SystemExit(
                f"The run finished, but scoring failed ({type(e).__name__}): {short_error(e)}\n"
                f"Score it later with: creativity-mapper --score-run {run_dir}"
            )


if __name__ == "__main__":
    main()
