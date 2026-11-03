from pathlib import Path
from typing import Any, Tuple

from crewai import LLM, Agent, Task
from crewai.tasks.task_output import TaskOutput

from creativity_mapper.observability import logger
from creativity_mapper.report import (
    clean_markdown,
    count_domain_mentions,
    domain_pattern,
    preserve_line_breaks,
)


MAX_BRIEF_REWRITES = 3

FORMAT_RULES = (
    " Use the section and field names exactly as written, leaving out any "
    "parenthetical hints. Return plain Markdown and do not wrap the document in a "
    "code fence."
)

ANALYTIC_RULE = " Write in a neutral, analytical register with no humor or stylistic flourish."
CREATIVE_RULE = (
    " Choose the voice and tone that best fits each concept; do not force a single style."
)


def save_to(path: Path, poetry: bool = False):
    """Callback that writes a task's output to `path`.

    With `poetry`, line breaks inside stanzas are preserved when rendered.

    CrewAI's `output_file` strips the leading slash from absolute paths, which
    would write relative to the current directory, so we save the file ourselves.
    """

    def _save(output: TaskOutput) -> None:
        text = clean_markdown(output.raw)
        path.write_text(preserve_line_breaks(text) if poetry else text, encoding="utf-8")

    return _save


def explore_phenomenon(agent: Agent, run_dir: Path) -> Task:
    return Task(
        description=(
            "Research the domain of {primary_domain}. Select one singular, specific, "
            "and unexpected phenomenon. Avoid famous textbook examples. Write a detailed "
            "summary of its rules, causes, and effects, naming each distinct component "
            "(actors, forces, conditions, outcomes) so it can later be mapped onto "
            "another domain."
        ),
        expected_output=(
            "A Markdown report with a title naming the phenomenon and these sections: "
            "Overview, Rules, Causes, Effects, Key Components (a list of every actor, "
            "force, condition and outcome with a one-line description each)."
            + FORMAT_RULES
            + ANALYTIC_RULE
        ),
        agent=agent,
        callback=save_to(run_dir / "01_phenomenon.md"),
    )


def map_to_target(agent: Agent, run_dir: Path, phenomenon: Task) -> Task:
    return Task(
        description=(
            "Using the phenomenon report, map its specific mechanics onto the domain of "
            "{target_domain}. Produce a 1:1 structural analogy: every component, rule, "
            "cause, and effect of the original phenomenon needs a clearly defined "
            "{target_domain} equivalent. Do not skip components, and keep the mapping "
            "concrete (real institutions, actors, instruments, or processes)."
        ),
        expected_output=(
            "A Markdown report with a title and these sections: Summary of the "
            "Phenomenon, Mapping Table (a Markdown table with columns "
            "'Original Component', 'Role in Phenomenon', '{target_domain} Equivalent', "
            "'Why It Fits', covering every Key Component), How the Mapped System "
            "Behaves (the full mechanism told in {target_domain} terms)."
            + FORMAT_RULES
            + ANALYTIC_RULE
        ),
        agent=agent,
        context=[phenomenon],
        callback=save_to(run_dir / "02_mapping.md"),
    )


def critique_mapping(agent: Agent, run_dir: Path, mapping: Task) -> Task:
    return Task(
        description=(
            "Critique the analogy between {primary_domain} and {target_domain}. "
            "Identify where the mapping breaks down or is logically inconsistent, where "
            "it reveals surprising practical insights, and evaluate whether the mapped "
            "concept could exist or be implemented in the real world. Refer to specific "
            "rows of the mapping by name."
        ),
        expected_output=(
            "A Markdown report with a title and these sections: Where the Mapping Holds, "
            "Where It Breaks Down, Surprising Insights, Real-World Feasibility "
            "(obstacles, requirements, and a verdict), Overall Assessment (a score out "
            "of 10 with a one-paragraph justification)."
            + FORMAT_RULES
            + ANALYTIC_RULE
        ),
        agent=agent,
        context=[mapping],
        callback=save_to(run_dir / "03_critique.md"),
    )


def distill_brief(
    agent: Agent,
    run_dir: Path,
    mapping: Task,
    critique: Task,
    primary: str,
    target: str,
    llm: LLM,
) -> Task:
    """Rewrite the mapped concept in target-domain terms only.

    Every creative task reads this brief and nothing upstream of it, which keeps the
    two domains decoupled. `primary` is used only to warn if the brief still names it.
    """
    path = run_dir / "03b_target_brief.md"
    save = save_to(path)

    def save_and_check(output: TaskOutput) -> None:
        save(output)
        leaked = count_domain_mentions(run_dir, primary, [path.name]).get(path.name, 0)
        if leaked:
            logger.warning("brief still mentions %r %d time(s)", primary, leaked)

    attempts = 0

    def foreign_terms(draft: str) -> list[str]:
        """Ask the model which words in the draft belong to the primary domain.

        Names can be matched by pattern, but technical jargon (a "catalyst" or "redox
        potential" in a boardroom) can only be recognized by reading it.
        """
        reply = llm.call(
            f"Below is a brief that is supposed to be written purely in the language of "
            f"{target}. List every word or phrase in it that comes from {primary} or from "
            f"another technical field (science, engineering, medicine, etc.) and would "
            f"sound out of place in an ordinary conversation among {target} "
            f"practitioners. Reply with only a comma-separated list of those words and "
            f"phrases, or the single word NONE if there are none.\n\n---\n{draft}"
        )
        reply = str(reply).strip()
        if not reply or reply.upper().startswith("NONE"):
            return []
        return [term.strip(" .*`\"'") for term in reply.split(",") if term.strip()][:15]

    def no_primary_terms(output: TaskOutput) -> Tuple[bool, Any]:
        """Ask for a rewrite while the brief leans on the primary domain; give up gracefully."""
        nonlocal attempts
        attempts += 1
        problems = sorted(set(domain_pattern(primary).findall(output.raw)))
        problems += foreign_terms(output.raw)
        if not problems or attempts > MAX_BRIEF_REWRITES:
            if problems:
                logger.warning("brief accepted with leftover primary-domain terms: %s", problems)
            return True, output
        logger.warning("brief rewrite %d requested; foreign terms: %s", attempts, problems)
        return False, (
            f"The brief still uses vocabulary from {primary} or technical fields: "
            f"{', '.join(problems)}. Rewrite it so none of these (or similar words) appear; "
            f"express every idea, limit and insight in plain {target} language."
        )

    return Task(
        description=(
            "Using the mapping and the critique, write a self-contained brief about the "
            "concept as if it had always belonged to {target_domain}. The writers who "
            "read your brief will never see the original {primary_domain} phenomenon, "
            "the mapping table or the critique, so everything they need must be in your "
            "brief, in {target_domain} language. Give the concept a name native to "
            "{target_domain}. Replace every original component with its {target_domain} "
            "equivalent. Never use {primary_domain} terminology, organisms, materials, physical or "
            "scientific laws or jargon, and never describe the concept as an analogy, "
            "mapping or metaphor for anything. If a word would sound out of place in an "
            "ordinary conversation among {target_domain} practitioners, replace it. "
            "The critique's breakdown points are mismatches between two domains; do not "
            "repeat them as such. Instead restate each one as a real constraint inside "
            "{target_domain} itself: what practical, human, organizational or "
            "technical factor in {target_domain} limits the concept, makes it fail, or "
            "makes it surprising. Do the same for the feasibility verdict. Before you "
            "finish, reread the brief and rewrite any sentence that still leans on "
            "{primary_domain}."
        ),
        expected_output=(
            "A Markdown report that opens with a '# <concept name>' heading, then these "
            "sections: The Concept (a short plain description), How It Works (its "
            "components, forces, sequence of events and outcomes), Where It Strains "
            "(limits, tensions and failure modes), Surprising Insights, Real-World "
            "Feasibility (obstacles and a verdict), Vocabulary (8-12 {target_domain} "
            "terms or invented names with a one-line meaning each, for writers to reuse)."
            + FORMAT_RULES
            + ANALYTIC_RULE
        ),
        agent=agent,
        context=[mapping, critique],
        guardrail=no_primary_terms,
        guardrail_max_retries=MAX_BRIEF_REWRITES,
        callback=save_and_check,
    )


def pitch_narratives(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, pitch exactly three distinct narrative "
            "concepts that use the brief's concept as a core plot device or "
            "world-building element. Each must be in a different genre which you will "
            "choose to best fit this concept. Use the "
            "{target_domain} setting and vocabulary from the brief, and let its "
            "breakdown points and insights drive conflict or twists."
        ),
        expected_output=(
            "A Markdown report with a title and exactly three concepts. Each concept is "
            "a section headed '## Concept 1: <title>', '## Concept 2: <title>' and '## Concept 3: <title>' with these fields in bold: Genre, "
            "Logline, Setting, How the Mechanism Drives the Plot, Main "
            "Characters, Central Conflict, Twist or Ending."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "04_narratives.md"),
    )


def pitch_products(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, brainstorm and outline exactly three "
            "distinct software applications, SaaS platforms, or commercial tech products "
            "that leverage the concept's core mechanics. Prefer ideas the brief found "
            "feasible, and address its obstacles where relevant. For each idea, define "
            "the target audience, core value proposition, and a basic MVP feature set."
        ),
        expected_output=(
            "A Markdown report with a title and exactly three products. Each product is "
            "a section headed '## Product 1: <name>', '## Product 2: <name>' and '## Product 3: <name>' with these fields in bold: Concept, Core Mechanic (which part of the concept it builds on), "
            "Target Audience, Core Value Proposition, MVP Features, Key Risk. "
            "Concept is 2-3 sentences and MVP Features is a bulleted list of 4-6 items."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "05_products.md"),
    )


def write_poems(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, write exactly three distinct poems "
            "inspired by the {target_domain} concept in the brief. Each poem must "
            "use a different form (for example sonnet, haiku sequence, villanelle, free "
            "verse, limerick set, ode) and take a different angle on the idea. Draw "
            "imagery from the {target_domain} vocabulary in the brief, and let its "
            "strains and insights provide tension or a turn."
        ),
        expected_output=(
            "A Markdown report with a title and exactly three poems. Each poem is a "
            "section headed '## Poem 1: <title>', '## Poem 2: <title>' and "
            "'## Poem 3: <title>', followed by one italic line naming its form, then "
            "the poem itself with one line of verse per line and a blank line between "
            "stanzas."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "06_poems.md", poetry=True),
    )


def write_lyrics(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, write the lyrics for one complete song "
            "inspired by the {target_domain} concept in the brief. Choose a genre "
            "and mood that suit the idea. Tell a small story or express one clear "
            "feeling, use imagery from the {target_domain} vocabulary in the brief, "
            "and let its tensions inform the bridge or final verse. The "
            "lyrics must scan when sung, with a memorable chorus."
        ),
        expected_output=(
            "A Markdown report with a title, then one italic line giving the genre, "
            "tempo and mood, then the lyrics in sections headed '### Verse 1', "
            "'### Chorus', '### Verse 2', '### Chorus', '### Bridge' and "
            "'### Final Chorus', with one line of lyric per line and the chorus repeated "
            "in full each time. End with a section '## Production Notes' of 3-5 "
            "bullets on instrumentation, arrangement and vocal style."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "07_lyrics.md", poetry=True),
    )


def write_comic(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, script a six-panel comic that tells the "
            "{target_domain} concept in the brief as a short story with a "
            "beginning, middle and end. The output is panel descriptions to be used "
            "as prompts for an AI image generator, not the art itself. Because a "
            "generator remembers nothing between images, every image prompt must be fully "
            "self-contained: restate each character's fixed visual description, the "
            "setting, and the style keywords in every panel. Keep all words, signs "
            "and speech bubbles out of the image prompts; lettering is added later."
        ),
        expected_output=(
            "A Markdown report that opens with a '# <title>' heading, then a '## Style Guide' section with these "
            "fields in bold: Art Style, Color Palette, Aspect Ratio, Characters (each "
            "with a fixed, detailed visual description). Then six sections headed "
            "'## Panel 1: <short title>' through '## Panel 6: <short title>', each with "
            "these fields in bold: Image Prompt (one self-contained paragraph covering "
            "subject, action, setting, shot type, composition, lighting, color and style), "
            "Lettering (the caption or dialogue to add afterwards, or 'None'), Avoid "
            "(a short list of things to exclude from the image)."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "08_comic.md"),
    )


def write_podcast(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, write the script for one episode of a "
            "fictional podcast that explores the {target_domain} "
            "concept in the brief. Invent the show, its hosts and any guests; all people must be "
            "fictional. The conversation should explain the concept accurately, include "
            "genuine disagreement drawn from the brief's strains, and sound like spoken "
            "language rather than an essay."
        ),
        expected_output=(
            "A Markdown report that opens with a '# <episode title>' heading, then a line "
            "in bold naming the show, its tagline and the episode length, then a "
            "'## Cast' section listing each host and guest with a one-line description. "
            "Then the script in sections headed '## Cold Open', '## Segment 1: <title>', "
            "'## Segment 2: <title>', '## Segment 3: <title>' and '## Outro'. Write each "
            "line of dialogue as '**NAME:** what they say' on its own line, with sound "
            "or music cues in italics inside square brackets."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "09_podcast.md"),
    )


def write_musical(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, write a condensed one-act satirical "
            "musical about the {target_domain} concept in the brief. Satirize the "
            "institutions, incentives and absurd behavior of {target_domain} that the "
            "brief exposes, and mine its strains and failure modes for comedy. All "
            "characters must be fictional; do not target real named people. Include "
            "three songs that move the story forward, with lyrics that scan when sung."
        ),
        expected_output=(
            "A Markdown report that opens with a '# <musical title>' heading, then a "
            "one-sentence logline in italics, then '## Characters' (each fictional "
            "character with a one-line description and vocal type), '## Setting', and "
            "three scenes headed '## Scene 1: <title>', '## Scene 2: <title>' and "
            "'## Scene 3: <title>'. Each scene has a short stage direction in italics, "
            "dialogue lines written as '**NAME:** what they say' on their own lines, and "
            "one song headed '### Song N: <title>' (numbered 1 to 3 across the scenes) "
            "preceded by a line in bold reading '**Sung by:** NAME' (or the names of the "
            "singers). Put the lyrics as plain lines of text, one lyric per line, with "
            "no speaker labels inside the song. Never use '#' heading syntax for "
            "dialogue or lyrics, only for the headings listed above."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "10_musical.md", poetry=True),
    )


def design_game(agent: Agent, run_dir: Path, brief: Task) -> Task:
    return Task(
        description=(
            "Using the brief, design one interactive desktop game "
            "(keyboard and mouse, played in a single sitting or as a short campaign) "
            "whose core mechanics are the {target_domain} concept in the brief. The player should feel the mechanism by playing "
            "it. Use the brief's strains and limits to create difficulty, twists or "
            "design limits. Also build the fictional world the game is set in, with "
            "its own history, factions, places and vocabulary, so the rules feel "
            "native to it."
        ),
        expected_output=(
            "A Markdown report that opens with a '# <game title>' heading and an italic "
            "one-sentence pitch, then these sections: '## Overview' (genre, platform, "
            "target audience, session length), '## Core Loop', '## Mechanics' (each "
            "mechanic as a bullet naming the part of the concept it comes from), "
            "'## Player Experience' (verbs, progression, win and lose conditions), "
            "'## A Sample Session' (a short play-by-play), '## World and Lore' with "
            "subsections '### History', '### Factions', '### Key Places' and "
            "'### Glossary' (6-10 terms), '## Art and Audio Direction' and "
            "'## MVP Scope' (what to build first, as a bulleted list)."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "11_game.md"),
    )


def compile_found_documents(
    agent: Agent, run_dir: Path, brief: Task
) -> Task:
    return Task(
        description=(
            "Using the brief, tell a story inspired by the "
            "{target_domain} concept in the brief as a dossier of six fictional "
            "found documents. Choose varied document types that suit the story (for "
            "example memo, email thread, field notes, transcript, incident report, "
            "classified ad, letter, meeting minutes). Each document has its own author, "
            "voice and agenda. The plot must emerge from the documents, through "
            "what the authors know, hide, misunderstand or leave unsaid, and through "
            "how the documents contradict or echo each other; never explain the story "
            "outright. Let the concept's mechanism drive events and the brief's "
            "strains create the mystery or the failure. All people and "
            "organizations are fictional."
        ),
        expected_output=(
            "A Markdown report that opens with a '# <dossier title>' heading, then a "
            "short italic note from the fictional archivist who assembled it, then six "
            "sections headed '## Document 1: <type> - <title>' through "
            "'## Document 6: <type> - <title>', in an order that withholds and reveals. "
            "Each document begins with a few bold metadata fields (such as Date, From, "
            "To, Subject or Classification, as suits its type) and then the document "
            "text in its own voice, using redactions like [REDACTED] and handwritten "
            "margin notes in italics where they help. The report ends with a "
            "'## Archivist's Closing Note' of two or three sentences that leaves the "
            "question open."
            + FORMAT_RULES
            + CREATIVE_RULE
        ),
        agent=agent,
        context=[brief],
        callback=save_to(run_dir / "12_found_documents.md"),
    )
