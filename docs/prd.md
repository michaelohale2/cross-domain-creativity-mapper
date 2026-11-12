Product Name: Cross-Domain-Creativity-Mapper

Platform: Command Line Interface (CLI) / VSCode Environment

Core Framework: CrewAI

LLM Backend: Gemini

1. Product Overview
Cross-Domain-Creativity-Mapper is a multi-agent CLI application for lateral thinking and concept mapping. Given two unrelated domains, it finds an obscure or highly unusual phenomenon in the primary domain and translates its underlying mechanics into the target domain. A sequential pipeline of 14 CrewAI agents then produces three kinds of Markdown output: analytical reports (the phenomenon, the mapping and a critique of its feasibility), a target-domain-only brief, and ten creative works built on that brief (narratives, software products, poems, song lyrics, a comic, a podcast script, a satirical musical, a game design, a found-document story and a 2-3 paragraph novel pitch). An optional LLM judge scores how creative a run is.

2. User Flow & System Execution
Initialization: The user runs `uv run creativity-mapper` (or `python -m creativity_mapper.main`) from the terminal.

Data Input: The two domains are given as positional arguments, or the CLI prompts for them:

Primary Domain (e.g., Biology, Quantum Physics)

Target Domain (e.g., Politics, Macroeconomics)

Options:

- `-v` / `--verbose`: show full agent output.
- `--only AGENT` (repeatable): run only the named creative agent(s) after the analytical steps. IDs ignore case and punctuation and accept the agent name ("Poet"), an alias ("poems") or the report number ("06").
- `-b` / `--benchmark`: score the run with the creativity benchmark when it finishes.
- `--score-run RUN_DIR`: score an existing run folder without generating anything. Cannot be combined with domains, `--benchmark` or `--only`.

Environment Setup: The script creates a timestamped run directory, output/[Primary]_[Target]_[YYYYMMDD_HHMMSS]/, so repeated runs never overwrite each other. Domain names are reduced to letters, digits and underscores. A run.log is written there.

Agent Handoff: The CrewAI sequential process runs the pipeline in section 4. Every agent shares one LLM. Per-step progress and duration are printed, and a heartbeat line appears every 15 seconds during a long step.

Output Generation: Each report is written as formatted Markdown as soon as its agent finishes. At the end, an index README.md is written with links to the reports and a per-step token table (input, output and reasoning tokens).

Benchmark (optional): If requested, the judge scores the run and writes creativity_benchmark.md and creativity_benchmark.json, plus a summary line in the run's README.md.

3. Architecture & Technical Stack
Language: Python 3.12+, managed with uv (hatchling build; console script `creativity-mapper`).

Orchestration: CrewAI (Sequential Process model).

LLM Integration: Gemini via crewai[google-genai]. Configured in .env:

- GEMINI_API_KEY (required)
- MODEL (default gemini/gemini-2.5-flash)
- JUDGE_MODEL (optional; defaults to MODEL; a separate, stronger model is recommended)
- LLM_TIMEOUT_SECONDS (default 120)

File System: Python pathlib for directory creation and file writing. Reports are saved by a custom task callback, because CrewAI's output_file strips absolute paths.

Reliability and Observability:

- A per-request timeout on the Google client, with up to 3 HTTP attempts, and agent-level retries of timed-out calls.
- run.log with step timings, token counts and library warnings.
- A heartbeat during long steps.
- Readable messages for a missing or invalid key, network failure, and Ctrl+C.
- If a step fails, the failed step is named and reports already written are kept.

4. Agent Definitions & Task Specifications
Steps 1-3 are analytical. Their register is neutral and critical so the user can examine the ideas. Steps 4-13 choose whatever voice and tone best serve each concept; there is no user-set tone option.

Agent 1: The Phenomenon Explorer
Reads: the primary domain. Writes: 01_phenomenon.md.
Goal: Select a singular, specific and unexpected phenomenon and explain its rules, causes and effects.

Agent 2: The Analogical Mapper
Reads: report 1. Writes: 02_mapping.md.
Goal: Map the phenomenon's mechanics onto the target domain as a 1:1 structural analogy (a table), defining the target-domain equivalent of every component.

Agent 3: The Analytical Critic
Reads: report 2. Writes: 03_critique.md.
Goal: Critique the mapping: where it breaks down, what practical insights it reveals, and whether the concept could exist in the real world.

Agent 3b: The Concept Distiller
Reads: reports 2 and 3. Writes: 03b_target_brief.md.
Goal: Rewrite the mapped concept as a self-contained brief in target-domain language only: a native name, every component translated, and the critique's breakdown points restated as constraints inside the target domain.
Guardrail: the draft is checked for the primary domain's name and, by a short LLM review, for technical vocabulary that would sound out of place in the target domain. It is sent back for up to 3 rewrites, then accepted with a warning.

Decoupling requirement: Agents 4-13 read only the brief. They never see the primary domain, the mapping table or the critique, so the creative outputs carry target-domain context only. Some terminology may slip through and that is acceptable. At the end of a run, the count of primary-domain name mentions in the creative reports is printed and logged.

Creative agents (each reads only the brief):

| # | Agent | Output | Deliverable |
| --- | --- | --- | --- |
| 4 | Narrative Designer | 04_narratives.md | Three distinct narrative concepts (e.g., hard sci-fi, steampunk, alternate history, dystopian thriller) using the concept as a core plot device or world-building element |
| 5 | Product Builder | 05_products.md | Three software or commercial tech products, each with target audience, value proposition and MVP features |
| 6 | Poet | 06_poems.md | Three poems |
| 7 | Lyricist | 07_lyrics.md | One song's lyrics |
| 8 | Comic Scripter | 08_comic.md | One comic as panel-by-panel image-generator prompts (the output is the prompt, not the art) |
| 9 | Podcast Scriptwriter | 09_podcast.md | A fictional podcast episode script |
| 10 | Satirical Musical Writer | 10_musical.md | A satirical musical script, with lyrics |
| 11 | Game Designer | 11_game.md | A desktop interactive game design with world-building lore |
| 12 | Found-Document Storyteller | 12_found_documents.md | A story told through found documents (letters, memos, logs, etc.) |
| 13 | Story Pitch Writer | 13_pitch.md | A 2-3 paragraph pitch for one original novel built on the concept, written to win over an agent or publisher |

5. Partial Runs (`--only`)
Agents 1-3b always run, since every creative agent depends on the brief. With `--only`, just the chosen creative agents run after them. The run README records that the run was partial and which agents ran (a visible note plus a machine-readable comment, `<!-- creative-reports: ... -->`), and the progress count and token table reflect only the steps that ran.

6. Creativity Benchmark
An LLM-as-judge scores a run on three criteria, each 1-10:

- Semantic Distance: how bold and unexpected the jump between the two domains is, and whether the mapping exploits it non-obviously. Judged once per run, on the phenomenon and mapping.
- Metaphorical Density: how deeply the concept's mechanics are built into a piece rather than name-dropped. Judged per creative report.
- Freedom from Cliché: whether the piece avoids stock AI phrasing, corporate buzzwords and predictable story shapes. Judged per creative report.

Creativity Index (out of 30) = Semantic Distance + mean Metaphorical Density + mean Freedom from Cliché.

Judge design: temperature 0, written anchors for each score level, and any cliché the judge quotes must appear in the text (invented quotes are dropped). Judge calls are retried on network errors; a report that still cannot be scored shows as n/a, and scoring stops with a message if the judge stays unreachable. Scoring never alters the reports and can be repeated with `--score-run`.

A partial run is scored on only the reports it produced. The benchmark output flags the index as partial, because it is noisier and not comparable with full-run indexes.

7. Output Specifications
All deliverables are Markdown files in the run directory:

```
output/[Primary]_[Target]_[YYYYMMDD_HHMMSS]/
  README.md            index, token usage, benchmark summary
  run.log
  01_phenomenon.md
  02_mapping.md
  03_critique.md
  03b_target_brief.md
  04_narratives.md ... 13_pitch.md
  creativity_benchmark.md / .json   (only if scored)
```

Reports are post-processed for consistent formatting: whole-document code fences are removed, consecutive bold fields are separated into paragraphs, and poetry, lyrics and musical lyrics keep their line breaks. Each file gets a header with the domains and date.

8. Known Limitations
- The judge defaults to the same model as the generator, which tends to score its own style generously. Set JUDGE_MODEL to a different model for fairer scores.
- The brief guardrail can use all 3 rewrite rounds on hard domain pairs and can over-flag ordinary target-domain words, which makes single-agent runs spend most of their tokens on the brief.
- The decoupling count matches the primary domain's name only, not its jargon.
- There is no resume option, and the creative steps run sequentially even though they are independent.
- Web search tools are not used. Agent 1 relies on the model's own knowledge.
