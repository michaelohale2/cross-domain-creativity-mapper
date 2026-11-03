# Implementation Plan: Cross-Domain-Creativity-Mapper

Reference: [prd.md](prd.md). Each step ends with a concrete check so it can be verified before moving on. Run everything with `uv run`.

## Current state

- Python 3.12 project managed by `uv`; `crewai[google-genai]` and `python-dotenv` installed.
- Stub entry point at `src/creativity_mapper/main.py`; `output/` exists; `.env.example` has `GEMINI_API_KEY`.

## Target layout

```
src/creativity_mapper/
  main.py       # CLI: prompt, setup, kick off crew
  config.py     # env loading, LLM factory
  paths.py      # domain sanitizing, run directory creation
  agents.py     # five agent factories
  tasks.py      # five task factories (output_file routed per run)
  crew.py       # assemble + run the sequential crew
tests/
  test_paths.py
```

## Steps

### 1. Config and LLM connectivity
- `config.py`: load `.env` with `python-dotenv`, fail with a clear message if `GEMINI_API_KEY` is missing.
- Build a shared `crewai.LLM` for Gemini (model name read from an optional `GEMINI_MODEL` env var, with a sensible default).
- **Check:** a one-off script calls `llm.call("Say hi")` and prints a response.

### 2. Run directory helper
- `paths.py`: sanitize a domain string (strip, replace whitespace/punctuation with `_`, reject empty) and create `output/[Primary]_[Target]/` with `pathlib`, returning the `Path`.
- Decide behavior when the directory exists (default: reuse and overwrite files; revisit if it matters).
- **Check:** `tests/test_paths.py` covers spaces, slashes, unicode, empty input, and an existing directory.

### 3. CLI input
- `main.py`: prompt for Primary Domain and Target Domain, re-prompt on blank input, then create the run directory.
- Print the output path so the user knows where results will land.
- **Check:** running the module prompts twice and creates the expected folder.

### 4. First agent and task end to end
- `agents.py` / `tasks.py`: implement Agent 1 (Phenomenon Explorer) and its task, with `{primary_domain}` and `{target_domain}` interpolated, and `output_file` pointing into the run directory.
- `crew.py`: a sequential `Crew` with just this one agent/task.
- **Check:** a real run writes `01_phenomenon.md` with a coherent summary of rules, causes, and effects.

### 5. Add Agents 2 and 3 (mapping and critique)
- Agent 2 consumes Agent 1's output via task `context`; produces a 1:1 component mapping (consider requiring a table).
- Agent 3 consumes Agent 2's output; covers breakdown points, surprising insights, and feasibility.
- **Check:** `02_mapping.md` and `03_critique.md` exist, and the critique visibly references specifics from the mapping.

### 6. Add Agents 4 and 5 (narrative and product)
- Both take Agent 2 and Agent 3 as `context` (not each other's output).
- Agent 4: three distinct narrative concepts. Agent 5: three software products, each with target audience, value proposition, and MVP features.
- **Check:** `04_narratives.md` and `05_products.md` each contain exactly three concepts with the required fields.

### 7. Output quality pass
- Tighten each task's `expected_output` to specify headings and structure so the Markdown is consistent across runs.
- Add a short header (domains, date) to each file or a generated `README.md` index in the run folder.
- Check that no file contains stray code fences wrapping the whole document.
- **Check:** two runs with different domain pairs both produce well-formed reports.

### 8. Robustness and UX
- Handle Ctrl+C, missing API key, and API errors with readable messages rather than tracebacks.
- Show progress (CrewAI `verbose` toggle via a `--verbose` flag).
- Optional: accept domains as CLI args (`argparse`) to skip prompts for scripted runs.

### 9. Docs and packaging
- Add `README.md`: setup (`uv sync`, copy `.env.example`), usage, example output tree.
- Add a `[project.scripts]` entry (e.g. `creativity-mapper`) so it runs as a command.
- Initialize git if desired and commit.

## Decisions to confirm early
- **Gemini model:** which model to default to (affects cost and quality).
- **Output file names:** numbered names above vs. descriptive names only.
- **Re-runs:** overwrite an existing run folder, or append a timestamp to keep history.
- **Tools:** the PRD says "research" for Agent 1; plain LLM knowledge is the default. Web search tools (e.g. Serper) could be added later but need another API key.

## Out of scope for the first version
Web UI, persistence beyond Markdown files, parallel or hierarchical crew processes, and multi-run comparison.
