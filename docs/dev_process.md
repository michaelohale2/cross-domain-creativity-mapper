# Development Process

How the Cross-Domain-Creativity-Mapper went from an empty folder to a thirteen-step CrewAI pipeline, in the order things happened. It was built iteratively with Claude Code: one small step at a time, run for real against Gemini after each step, with problems fixed as they surfaced.

## Outcome

A CLI that takes two domains (for example Geology and Jazz) and runs a sequential CrewAI crew of thirteen agents. Steps 1-3 and the target-domain brief are analytical; the other nine are creative.

| # | Agent | Output |
| --- | --- | --- |
| 1 | Phenomenon Explorer | `01_phenomenon.md` |
| 2 | Analogical Mapper | `02_mapping.md` |
| 3 | Analytical Critic | `03_critique.md` |
| 3b | Concept Distiller | `03b_target_brief.md` (the concept in target-domain terms only) |
| 4 | Narrative Designer | `04_narratives.md` (3 concepts) |
| 5 | Product Builder | `05_products.md` (3 products) |
| 6 | Poet | `06_poems.md` (3 poems) |
| 7 | Lyricist | `07_lyrics.md` (1 song) |
| 8 | Comic Scripter | `08_comic.md` (6 panels as image-generator prompts) |
| 9 | Podcast Scriptwriter | `09_podcast.md` (1 fictional episode) |
| 10 | Satirical Musical Writer | `10_musical.md` (1 one-act musical, 3 songs) |
| 11 | Game Designer | `11_game.md` (desktop game design plus world lore) |
| 12 | Found-Document Storyteller | `12_found_documents.md` (6-document dossier) |

Each run writes to `output/[Primary]_[Target]_[YYYYMMDD_HHMMSS]/` with an index `README.md` that includes a per-step token usage table. A typical full run uses about 40k tokens and takes several minutes.

## Timeline

### 1. Setup
- Chose `uv` for project management. The system Python was 3.14, so the first attempt was to pin 3.12.
- Installed `crewai[google-genai]` and `python-dotenv`. Created the layout (`src/creativity_mapper/`, `output/`, `docs/`), `.env.example` and `.gitignore`.
- Wrote `docs/plan.md`: nine steps, each ending in a concrete check.

### 2. Building the plan step by step
1. **Config and LLM:** `get_llm()` loads `.env`, fails clearly on a missing key, and returns a CrewAI `LLM`. A one-line test call confirmed Gemini worked.
2. **Run directory helper:** domain-name sanitizing (spaces and punctuation to underscores, path traversal made impossible) plus unit tests.
3. **CLI prompts:** re-prompt on blank input, clean exit on Ctrl+C or Ctrl+D.
4. **First agent end to end:** Phenomenon Explorer, Task, sequential Crew.
5. **Agents 2 and 3:** mapping and critique, chained with task `context`.
6. **Agents 4 and 5:** narratives and products, both reading the mapping and the critique.
7. **Quality pass:** consistent headings, stripping of wrapping code fences, a context header on each report, an index `README.md`.
8. **Robustness:** `argparse` with optional domain arguments and `--verbose`, short error messages, progress lines.
9. **Docs and packaging:** README and a `creativity-mapper` command.

### 3. Features added after the plan
- **Timestamped output folders**, because outputs are random and the same inputs get run repeatedly.
- **Observability** (after a run hung): request timeout and retries, a per-step duration and heartbeat on the console, and `run.log` in every run folder.
- **Per-step token usage** (input, output, reasoning) in each run's index.
- **Poems, lyrics, comic panels, podcast, satirical musical, game design, found documents**, one agent each. Everything after the critique reads only the mapping and the critique, so each creative agent works from the same validated idea.
- **Domain decoupling:** the creative agents were mixing both domains (podcast hosts arguing "stop trying to invent geology", a musical character obsessed with geological metaphors). See the section below.
- **Analytical register for steps 1-3:** the user wanted to explore the topic critically, so only the creative agents get creative latitude.

## Problems found and how they were solved

| Problem | Cause | Fix |
| --- | --- | --- |
| `import creativity_mapper` failed | `uv init --bare` creates no build system, so the package was never installed in the venv | Added hatchling build config and ran `uv sync` |
| Reports written to a stray `Users/michaelhale/...` folder inside the project | CrewAI's `output_file` validator strips the leading `/` from absolute paths, so the path became relative to the current directory | Replaced `output_file` with a task `callback` (`save_to`) that writes the file itself. Deviates from the PRD wording, but works from any working directory |
| Venv was Python 3.14, not the intended 3.12 | `requires-python = ">=3.12"` let `uv` pick 3.14, and no `.python-version` was written | Left as is. CrewAI runs fine on 3.14. Pin with `uv python pin 3.12` if needed |
| Field names leaked prompt hints, such as `**Concept (2-3 sentences):**` | Hints written in parentheses in `expected_output` were copied into the output | Moved hints out of field names and added a shared `FORMAT_RULES` instruction |
| Headings came out as `## Product N: ...` | The model copied the literal placeholder `N` | Spelled out `1`, `2` and `3` in the task text |
| Narrative fields merged into one paragraph | Consecutive `**Field:** value` lines with no blank line between them render as one paragraph in Markdown | `clean_markdown()` inserts blank lines between runs of bold-led lines |
| Poem and lyric lines merged | Same Markdown line-joining behavior | `preserve_line_breaks()` adds hard breaks for poetry-type reports only |
| A lyric line rendered as a heading in the musical | The model used `###` on a lyric | Task text now forbids heading syntax for dialogue and lyrics, and defines a `**Sung by:**` line |
| Comic report began with `## Title:` and the date header landed above it | The model skipped the `#` title | Task text now requires a `# <title>` opening heading |
| Token usage per step not available | CrewAI's `TaskOutput` carries no usage data, and all agents share one LLM | `RunTracker` snapshots the LLM's cumulative usage after each task and records the difference |
| Output tokens would not sum to the total | For Gemini, CrewAI's completion count already includes reasoning tokens | Report Output as completion minus reasoning |
| Noisy warnings hid the progress lines | Library logging and pydantic warnings | Originally silenced with `logging.disable`; later replaced by routing all logging to `run.log` (see below) |
| A run sat for 11+ minutes at step 7 with 0% CPU | One Gemini request stalled. CrewAI's Gemini provider ignores its `timeout` setting, and the Google client has no default timeout, so the call waited forever. Silenced logging hid any clue | Set `HttpOptions(timeout=...)` on the Google client via `client_params` (default 120s, `LLM_TIMEOUT_SECONDS`). A timed-out call is retried by the agent (`max_retry_limit`, default 2), confirmed against a local server that accepts connections and never replies. Added a heartbeat and `run.log` |

## Decoupling the two domains

Request: outputs 4-12 should live in the target domain only, with the primary domain kept out as far as possible.

1. **Diagnosis.** The leak was structural. Every creative agent received the mapping table (which has an "Original Component" column) and the critique (which is entirely about mismatches between the domains), and nine prompts said "the {primary} to {target} concept". Prompting alone could not remove terms that were in the context.
2. **Fix, part 1: a brief.** A new analytical agent, the Concept Distiller (`03b_target_brief.md`), rewrites the concept in target-domain language only. Steps 4-12 read only the brief; every mention of the primary domain, the mapping or the critique was removed from their prompts.
3. **Measurement.** The first version cut mentions of the primary domain's name from 38 to 12 in a Geology/Jazz comparison, but reading the output showed the brief still carried the source's jargon (a corporate brief with "high-redox-potential reviews" and "aliphatic assets"), because the critique's breakdown points were passed through as cross-domain mismatches.
4. **Fix, part 2: better instructions and a guardrail.** The distiller is told to restate each breakdown point as a real constraint inside the target domain and to drop words that would sound out of place there. A CrewAI task guardrail checks the draft: a pattern match for the primary domain's name, plus a short model call that lists foreign technical vocabulary. If anything is found, the list goes back to the agent for a rewrite (up to 3 times, then the brief is accepted with a warning in `run.log`, so a stubborn response cannot fail the run).
5. **Result** (Mycology → Corporate Governance): the auditor requested two rewrites on its way to a brief written purely in boardroom terms; zero mentions of the domain name and one stray phrase ("evolutionary biology") across all nine creative reports. Token cost was about the same as before: the brief step is expensive (about 11k tokens), but each creative step now reads a shorter input.

Lessons: put a translation step between the analysis and the creative work rather than relying on instructions; the name of a domain is easy to detect by pattern but its jargon is not, so jargon needs a model to review it; and a metric that only matches names gives false comfort, so read the outputs too.

## Creativity benchmark

Request: add a benchmark scoring semantic distance, metaphorical density and freedom from cliché, starting from a draft judge prompt.

**Design changes to the draft prompt**
- **Where each criterion is scored.** Semantic distance belongs to the domain pair and the chosen mapping, and the creative outputs no longer mention the primary domain at all, so it is scored once per run on the phenomenon and mapping. Metaphorical density and cliché are scored for each of the nine creative reports, which also shows which formats are strongest.
- **Index.** Semantic distance + mean density + mean cliché-freedom, out of 30.
- **Anchored rubric.** Each criterion has written descriptions of what 1-3, 4-6, 7-9 and 10 look like, plus an instruction that typical LLM output deserves 3-6, to push back on the usual inflated scores.
- **Judge model.** Configurable through `JUDGE_MODEL` (falls back to `MODEL`), run at temperature 0, since a model rates its own style generously.
- **Output.** `creativity_benchmark.md` and `.json` per run, plus a summary in the run's README. `--benchmark` scores after a run; `--score-run PATH` scores an old run with no generation (the domains are read from the run's README heading). Runs from before the brief existed fall back to the mapping.

**What testing found**
- **The judge parroted its own instructions.** In the first real scoring it listed "ecosystem" and "seamless" as clichés in a product report that contained neither; "seamless" was an example in the prompt. It also cited the template's own field label ("MVP Features"). Fixes: the prompt now says examples are not evidence and that headings and field labels are never judged, and the code checks every quoted cliché against the text and drops the ones that are not there.
- **Consistency.** Scoring the same run twice: index 21.0 then 20.3, average change 0.28 per score.
- **Validity at the low end.** A hand-written cliché-ridden piece ("neon-soaked dystopia", "tapestry", "Dr. Elena Vance", "the AI was behind it all") scored 1/1, for an index of 4/30, with every quoted cliché found in the text.
- **Format differences** in the first scored run: found documents (9, 9) and poems were strongest, product pitches weakest (3, 3), mostly for stock SaaS phrasing.

- **Failure handling (found in use).** A DNS failure (`nodename nor servname provided, or not known`) killed a scoring pass outright. The pipeline's agents retry failed calls, but the judge called the model directly, so it had no retries and lost all progress; a failed `--benchmark` would also have reported "Run failed" for a run that had succeeded. Now judge calls retry with backoff, an isolated unreachable report becomes n/a, scoring aborts after two consecutive unreachable calls, and a failure after a successful run says the run finished and how to re-score. A test caught that the backoff was binding `time.sleep` too early to be patched (the tests slept for real, 34s).

**Caveats.** The judge is the same model that wrote the work unless `JUDGE_MODEL` is set; the semantic distance score looked generous (9 for fungal predation mapped to hostile takeovers, a fairly familiar analogy), which a stronger judge may fix; the judge's free-text evidence is not verified, only its quoted clichés.

## Decisions and reversals

- **Tone input (added, then removed):** a per-run tone (Hilarious, Academic, Satirical, and so on) was added and wired through all agents. Then it was narrowed to the creative agents only, tried on a real run, and finally removed. A single forced tone usually did not fit the content, so the creative agents now choose whatever voice suits each idea. The analytical agents stay neutral.
- **One item vs three:** narratives, products and poems produce three items each. The later creative formats (song, comic, podcast, musical, game, dossier) produce one each, since this is an experiment and each is already long.
- **Model choice:** the model is read from the `MODEL` environment variable. `.env` also holds `NEW_MODEL`, `EXPLORATION_MODEL`, `MAPPING_MODEL`, `CRITIQUE_MODEL` and `PITCH_MODEL`, which the code does not use yet.
- **Existing output folders:** earlier un-timestamped folders and test-run folders were left in `output/` (gitignored).

## Testing

- 45 unit tests (`uv run pytest`) cover domain sanitizing, timestamped directories, fence stripping, bold-line separation, header insertion, the run index, token usage tables, line-break preservation, observability helpers, domain-term counting and the benchmark's parsing, scoring math and file output.
- The LLM calls are not unit-tested. Every agent was checked by running the whole crew on real domain pairs (Biology/Politics, Quantum Physics/Macroeconomics, Geology/Jazz, and others) and reading the output.

## Known limitations and ideas

- **No git repo yet.** `git init` has not been run.
- **The benchmark has only been calibrated with the pipeline's own model as judge.** Try a stronger `JUDGE_MODEL` and compare.
- **Decoupling is best-effort.** The end-of-run count only matches the primary domain's name; jargon is reviewed by the model during the brief step and can still slip through occasionally.
- **Runs are sequential.** Steps 4-12 do not depend on each other and could run in parallel to cut the wait roughly in half.
- **Per-step models** are configured in `.env` but not wired in.
- **Agent 1 has no tools.** It works from the model's own knowledge. A web search tool could ground the phenomenon, at the cost of another API key.
- **An interrupted or failed run** writes no index or token table. The finished reports are kept, but without headers.
- **A bad API key** leaves an empty run folder, since the key is only validated on the first call.
- **No resume.** A failed or hung run cannot continue from its last finished step; a re-run starts over in a new folder.
- **Comic prompts** have been read but not tried in an image generator.
- **`docs/prd.md`** still describes the original five-agent design and the un-timestamped folder name.
