import os

from crewai import LLM
from dotenv import load_dotenv
from google.genai import types

DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_TIMEOUT_SECONDS = 120
HTTP_ATTEMPTS = 3
PROVIDERS = ("gemini", "local")
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def resolve_provider(provider: str | None = None) -> str:
    """The provider to use: the argument (from --provider), else LLM_PROVIDER, else gemini."""
    load_dotenv()
    value = (provider or os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    if value not in PROVIDERS:
        raise SystemExit(f"Unknown provider {value!r}; choose from: {', '.join(PROVIDERS)}.")
    return value


def get_local_llm(timeout: float, temperature: float | None = None) -> LLM:
    """An LLM served by a local Ollama server; `LOCAL_MODEL` names the model there."""
    model = os.getenv("LOCAL_MODEL")
    if not model:
        raise SystemExit("LOCAL_MODEL is not set. Add the Ollama model name to your .env file.")
    extra = {} if temperature is None else {"temperature": temperature}
    return LLM(
        model=f"ollama/{model.removeprefix('ollama/')}",
        base_url=os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA_URL,
        timeout=timeout,
        **extra,
    )


def get_llm(
    model_var: str = "MODEL", temperature: float | None = None, provider: str | None = None
) -> LLM:
    """Build the LLM for `provider` (local Ollama, or Gemini by default); `model_var` names the environment variable holding its model id.

    CrewAI's own `timeout` setting is ignored by its Gemini provider, so the limit is
    set on the underlying Google client. Without it a stalled request waits forever.
    A timed-out call is retried by the agent (CrewAI `max_retry_limit`, default 2);
    the client's retry option covers transient HTTP errors such as 429 and 503.
    """
    provider = resolve_provider(provider)
    try:
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        raise SystemExit("LLM_TIMEOUT_SECONDS must be a number of seconds.")

    if provider == "local":
        return get_local_llm(timeout, temperature)

    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")

    http_options = types.HttpOptions(
        timeout=int(timeout * 1000),
        retry_options=types.HttpRetryOptions(attempts=HTTP_ATTEMPTS),
    )
    model = os.getenv(model_var) or os.getenv("MODEL", DEFAULT_MODEL)
    extra = {} if temperature is None else {"temperature": temperature}
    return LLM(model=model, client_params={"http_options": http_options}, **extra)


def get_judge_llm(provider: str | None = None) -> LLM:
    """LLM used to score creativity: `JUDGE_MODEL` if set (else `MODEL`), at temperature 0.
    With the local provider the judge is the local model, since `JUDGE_MODEL` names a Gemini model.

    A separate, ideally stronger model is better, because a model tends to rate its own
    style generously.
    """
    return get_llm("JUDGE_MODEL", temperature=0, provider=provider)
