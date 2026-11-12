import pytest

from creativity_mapper import config
from creativity_mapper.config import get_judge_llm, get_llm, resolve_provider


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: None)  # ignore the real .env
    for var in ("LLM_PROVIDER", "LOCAL_MODEL", "OLLAMA_HOST", "GEMINI_API_KEY", "MODEL", "JUDGE_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_provider_defaults_to_gemini_and_the_flag_beats_the_env(monkeypatch):
    assert resolve_provider() == "gemini"
    monkeypatch.setenv("LLM_PROVIDER", "local")
    assert resolve_provider() == "local"
    assert resolve_provider("gemini") == "gemini"


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(SystemExit, match="Unknown provider"):
        resolve_provider()


def test_local_provider_uses_the_ollama_model_without_a_gemini_key(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL", "gemma4-crew")
    llm = get_llm(provider="local")
    assert llm.model == "gemma4-crew"
    assert "11434" in llm.base_url


def test_local_provider_requires_a_model():
    with pytest.raises(SystemExit, match="LOCAL_MODEL"):
        get_llm(provider="local")


def test_gemini_provider_still_requires_a_key():
    with pytest.raises(SystemExit, match="GEMINI_API_KEY"):
        get_llm(provider="gemini")


def test_judge_follows_the_provider(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL", "gemma4-crew")
    monkeypatch.setenv("JUDGE_MODEL", "gemini/some-judge")
    assert get_judge_llm("local").model == "gemma4-crew"
