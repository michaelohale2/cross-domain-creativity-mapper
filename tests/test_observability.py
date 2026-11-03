import logging
import time

from creativity_mapper.observability import Heartbeat, format_elapsed, setup_run_logging


def test_format_elapsed():
    assert format_elapsed(0) == "0s"
    assert format_elapsed(45.9) == "45s"
    assert format_elapsed(130) == "2m10s"
    assert format_elapsed(600) == "10m00s"


def test_run_log_captures_library_warnings(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        log_path = setup_run_logging(tmp_path)
        logging.getLogger("some.library").warning("rate limited, retrying")
        logging.getLogger("creativity_mapper").info("step started")
        for handler in root.handlers:
            handler.flush()
        text = log_path.read_text()
        assert log_path == tmp_path / "run.log"
        assert "rate limited, retrying" in text
        assert "step started" in text
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()


def test_heartbeat_reports_long_steps_only(capsys):
    with Heartbeat(lambda: ("Writing lyrics", 42), interval=0.05):
        time.sleep(0.2)
    assert "still working on 'Writing lyrics' (42s so far)" in capsys.readouterr().out

    with Heartbeat(lambda: ("Quick step", 1), interval=5):
        pass
    assert capsys.readouterr().out == ""


def test_heartbeat_repeats_each_interval_for_a_long_step(capsys):
    elapsed = iter(range(1, 1000))  # each poll sees the step one second older
    with Heartbeat(lambda: ("Slow step", next(elapsed)), interval=3, poll=0.01):
        time.sleep(0.2)
    lines = [l for l in capsys.readouterr().out.splitlines() if "Slow step" in l]
    assert len(lines) >= 3
    assert "(3s so far)" in lines[0]
    assert "(6s so far)" in lines[1]
