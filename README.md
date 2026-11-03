# Cross-Domain Creativity Mapper

A multi-agent CLI built on [CrewAI](https://www.crewai.com/) and Gemini. Give it two unrelated domains, and a thirteen-agent pipeline finds an unusual phenomenon in the first, maps its mechanics onto the second, critiques the mapping, then pitches stories, software products, poems, song lyrics and a comic (as image-generator prompts), a fictional podcast episode, a satirical musical, a desktop game design with world lore, and a story told through found documents built on it.

See [docs/prd.md](docs/prd.md) for the product definition and [docs/plan.md](docs/plan.md) for the implementation plan.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and a [Gemini API key](https://aistudio.google.com/apikey).

```sh
uv sync
cp .env.example .env   # then edit .env
```

`.env` settings:

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Required. Your Gemini API key. |
| `MODEL` | Optional. CrewAI model id, default `gemini/gemini-2.5-flash`. |
| `JUDGE_MODEL` | Optional. Model that scores creativity (see below); defaults to `MODEL`. A separate, stronger model is better. |
| `LLM_TIMEOUT_SECONDS` | Optional. Per-request timeout, default `120`. A request that stalls longer is cancelled and retried (up to 3 attempts per step) instead of hanging. |

## Usage

```sh
uv run creativity-mapper                        # prompts for both domains
uv run creativity-mapper Biology Politics       # skip the prompts
uv run creativity-mapper "Quantum Physics" Macroeconomics --verbose
```

When prompted, you are asked for the primary and target domains. The phenomenon, mapping and critique are written in a neutral, analytical register so you can examine the ideas critically; the narrative, product, poetry, lyrics, comic, podcast, musical, game and found-document agents choose whatever voice best fits each concept.

To generate just one kind of output, name the creative agent with `--only` (repeat it for a few). The analytical steps 1-3b always run first, because every creative agent works from the brief they produce, and then only the chosen agent runs:

```sh
uv run creativity-mapper Geology Jazz --only Poet
uv run creativity-mapper Geology Jazz --only Poet --only Lyricist --benchmark
```

Names ignore case and punctuation and accept the agent's name (`Poet`, `Game Designer`), a short alias (`poems`, `lyrics`, `game`, `musical`, `documents`) or the report number (`06`). Run `uv run creativity-mapper --help` for the full list. The run's `README.md` records that it was a partial run and which agents ran.

Quote domains that contain spaces. By default you see one progress line per agent; `-v` / `--verbose` shows full agent output. A run takes a few minutes. You can also run it with `uv run python -m creativity_mapper.main`.

## The pipeline

Agents run sequentially. Each report is written as soon as its agent finishes.

**Keeping the two domains apart.** Steps 1-3 work across both domains. The Concept Distiller (3b) then rewrites the mapped concept as a self-contained brief in *target-domain language only*: a native name, every component translated, and the critique's breakdown points restated as real constraints inside the target domain. All the creative agents (4-12) read only that brief and never see the primary domain, the mapping table or the critique. A guardrail checks the draft brief for the primary domain's name and, through a short model review, for technical vocabulary that would sound out of place in the target domain, and sends it back for up to 3 rewrites. A little terminology can still slip through; at the end of each run the number of primary-domain name mentions across the creative reports is printed and logged.

| # | Agent | Reads | Writes |
| --- | --- | --- | --- |
| 1 | Phenomenon Explorer | the primary domain | `01_phenomenon.md` |
| 2 | Analogical Mapper | report 1 | `02_mapping.md` |
| 3 | Analytical Critic | report 2 | `03_critique.md` |
| 3b | Concept Distiller | reports 2, 3 | `03b_target_brief.md` |
| 4 | Narrative Designer | the brief | `04_narratives.md` |
| 5 | Product Builder | the brief | `05_products.md` |
| 6 | Poet | the brief | `06_poems.md` |
| 7 | Lyricist | the brief | `07_lyrics.md` |
| 8 | Comic Scripter | the brief | `08_comic.md` |
| 9 | Podcast Scriptwriter | the brief | `09_podcast.md` |
| 10 | Satirical Musical Writer | the brief | `10_musical.md` |
| 11 | Game Designer | the brief | `11_game.md` |
| 12 | Found-Document Storyteller | the brief | `12_found_documents.md` |

## Output

Each run writes to `output/[Primary]_[Target]_[YYYYMMDD_HHMMSS]/`, with domain names reduced to letters, digits and underscores:

```
output/Biology_Politics_20261025_143005/
  README.md            index linking the reports, with token usage
  run.log              timestamped log of the run
  creativity_benchmark.md / .json   only if the run was scored
  01_phenomenon.md
  02_mapping.md
  03_critique.md
  03b_target_brief.md
  04_narratives.md
  05_products.md
  06_poems.md
  07_lyrics.md
  08_comic.md
  09_podcast.md
  10_musical.md
  11_game.md
  12_found_documents.md
```

The timestamp means repeated runs of the same domains never overwrite each other. The agents pick a phenomenon fresh each time, so results differ between runs. The `output/` folder is gitignored.

## Creativity benchmark

An LLM judge can score how creative a run is. Add `--benchmark` to score a run as soon as it finishes, or score an existing run folder later without generating anything:

```sh
uv run creativity-mapper Geology Jazz --benchmark
uv run creativity-mapper --score-run output/Geology_Jazz_20261026_130713
```

A partial run (`--only`) is scored on just the reports it produced; the run's README tells the scorer which, and the benchmark report flags the index as based on a partial set, so it is noisier and not comparable with full-run indexes. Three criteria, each 1-10:

| Criterion | Judged on | Question |
| --- | --- | --- |
| Semantic Distance | the phenomenon and mapping, once per run | How bold and unexpected is the jump between the two domains, and does the mapping exploit it in a non-obvious way? |
| Metaphorical Density | each of the 9 creative reports | How deeply are the concept's mechanics built into the piece, rather than name-dropped? |
| Freedom from Cliché | each of the 9 creative reports | Did it avoid stock AI phrasing, corporate buzzwords and predictable story shapes? |

The **Creativity Index** (out of 30) is Semantic Distance plus the mean Metaphorical Density plus the mean Freedom from Cliché. Results go to `creativity_benchmark.md` (scores by format, the judge's notes, the clichés it found), `creativity_benchmark.json` (for comparing runs) and a summary line in the run's `README.md`. Scoring a run takes about a minute and roughly 27k tokens. Judge calls are retried (3 attempts with a short wait) on network errors; if a single report still cannot be scored it shows as n/a and the rest carry on, and if the judge stays unreachable scoring stops with a message. Reports are never affected, and you can re-score at any time with `--score-run`.

How far to trust it: the judge runs at temperature 0, scores against written anchors for each level, and must quote clichés that really appear in the text (quotes it invents are dropped). Scoring the same run twice moved individual scores by about 0.3 points on average, and a deliberately cliché-ridden piece scored 4/30 against 20-21 for real runs. It is still an LLM judge: it is noisy by a point or so, it tends to favor its own style, and scores are only comparable between runs scored by the same judge model.

## Watching a run

- Each step prints its duration when it finishes, for example `[4/12] Writing narratives complete (7s)`.
- If a step runs longer than 15 seconds, a `... still working on 'Writing lyrics' (30s so far)` line is printed every 15 seconds, so you can tell a slow step from a stuck one.
- Every run writes `run.log` in its folder with timestamped step starts and finishes, token counts, each HTTP request to Gemini, and library warnings such as retries, timeouts and rate limits. Start there when something looks wrong.
- If a step still fails after its retries, the app names the step that failed and exits; reports finished before it are kept.

## Development

```sh
uv run pytest
```

Code lives in `src/creativity_mapper/`: `main.py` (CLI), `config.py` (env and LLM), `paths.py` (run folders), `agents.py`, `tasks.py`, `crew.py` (pipeline), `report.py` (Markdown cleanup and index).
