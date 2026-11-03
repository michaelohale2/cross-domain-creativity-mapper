import os

from crewai import LLM
from dotenv import load_dotenv
from google.genai import types

DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_TIMEOUT_SECONDS = 120
HTTP_ATTEMPTS = 3


def get_llm(model_var: str = "MODEL", temperature: float | None = None) -> LLM:
    """Build a Gemini LLM; `model_var` names the environment variable holding its model id.

    CrewAI's own `timeout` setting is ignored by its Gemini provider, so the limit is
    set on the underlying Google client. Without it a stalled request waits forever.
    A timed-out call is retried by the agent (CrewAI `max_retry_limit`, default 2);
    the client's retry option covers transient HTTP errors such as 429 and 503.
    """
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")

    try:
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        raise SystemExit("LLM_TIMEOUT_SECONDS must be a number of seconds.")

    http_options = types.HttpOptions(
        timeout=int(timeout * 1000),
        retry_options=types.HttpRetryOptions(attempts=HTTP_ATTEMPTS),
    )
    model = os.getenv(model_var) or os.getenv("MODEL", DEFAULT_MODEL)
    extra = {} if temperature is None else {"temperature": temperature}
    return LLM(model=model, client_params={"http_options": http_options}, **extra)


def get_judge_llm() -> LLM:
    """LLM used to score creativity: `JUDGE_MODEL` if set (else `MODEL`), at temperature 0.

    A separate, ideally stronger model is better, because a model tends to rate its own
    style generously.
    """
    return get_llm("JUDGE_MODEL", temperature=0)
