import re
from datetime import datetime
from pathlib import Path

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "output"


def sanitize_domain(name: str) -> str:
    """Collapse anything that isn't a letter or digit into single underscores."""
    cleaned = re.sub(r"\W+", "_", name.strip()).strip("_")
    if not cleaned:
        raise ValueError("Domain name must contain at least one letter or digit.")
    return cleaned


def create_run_dir(
    primary: str, target: str, root: Path = OUTPUT_ROOT, now: datetime | None = None
) -> Path:
    """Create output/[Primary]_[Target]_[YYYYMMDD_HHMMSS]/ and return its path.

    The timestamp keeps repeated runs of the same domains from overwriting each other.
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    run_dir = root / f"{sanitize_domain(primary)}_{sanitize_domain(target)}_{stamp}"
    run_dir.mkdir(parents=True)
    return run_dir
