from datetime import datetime, timedelta

import pytest

from creativity_mapper.paths import create_run_dir, sanitize_domain


def test_spaces_become_underscores():
    assert sanitize_domain("Quantum Physics") == "Quantum_Physics"


def test_slashes_and_punctuation_cannot_escape_root():
    assert sanitize_domain("../etc/passwd") == "etc_passwd"
    assert sanitize_domain("a/b\\c: d!") == "a_b_c_d"


def test_unicode_letters_are_kept():
    assert sanitize_domain("Économie") == "Économie"


@pytest.mark.parametrize("bad", ["", "   ", "///", "!!!"])
def test_empty_input_rejected(bad):
    with pytest.raises(ValueError):
        sanitize_domain(bad)


NOW = datetime(2026, 10, 25, 14, 30, 5)


def test_creates_timestamped_directory(tmp_path):
    run_dir = create_run_dir("Biology", "Macro Economics", root=tmp_path, now=NOW)
    assert run_dir == tmp_path / "Biology_Macro_Economics_20261025_143005"
    assert run_dir.is_dir()


def test_same_domains_at_different_times_get_separate_directories(tmp_path):
    first = create_run_dir("Biology", "Politics", root=tmp_path, now=NOW)
    second = create_run_dir("Biology", "Politics", root=tmp_path, now=NOW + timedelta(seconds=1))
    assert first != second
    assert first.is_dir() and second.is_dir()
