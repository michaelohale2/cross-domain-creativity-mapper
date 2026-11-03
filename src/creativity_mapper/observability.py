import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("creativity_mapper")

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
HEARTBEAT_SECONDS = 15


def format_elapsed(seconds: float) -> str:
    """Compact duration such as '45s' or '2m10s'."""
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


def setup_run_logging(run_dir: Path, verbose: bool = False) -> Path:
    """Send all logging (ours and the libraries') to run_dir/run.log.

    Library warnings such as retries and rate limits land here instead of being
    hidden or cluttering the console. With `verbose` they also go to stderr.
    """
    log_path = run_dir / "run.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_handler)

    if verbose:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(console)
    return log_path


class Heartbeat:
    """Prints and logs a still-working line while a single step runs long.

    `status` returns the current step's label and how many seconds it has run. A line
    is emitted each time a step passes another multiple of `interval`, so quick
    steps stay silent and a stalled one is reported every `interval` seconds.
    """

    def __init__(
        self,
        status: Callable[[], tuple[str, float]],
        interval: float = HEARTBEAT_SECONDS,
        poll: float | None = None,
    ):
        self._status = status
        self._interval = interval
        self._poll = poll if poll is not None else min(1.0, interval / 2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        reported: dict[str, int] = {}
        while not self._stop.wait(self._poll):
            label, elapsed = self._status()
            intervals = int(elapsed // self._interval)
            if intervals > reported.get(label, 0):
                reported[label] = intervals
                message = f"still working on '{label}' ({format_elapsed(elapsed)} so far)"
                logger.info(message)
                print(f"    ... {message}", flush=True)

    def __enter__(self) -> "Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
