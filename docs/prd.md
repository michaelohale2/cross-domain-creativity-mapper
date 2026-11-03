Product Name: Cross-Domain-Creativity-Mapper

Platform: Command Line Interface (CLI) / VSCode Environment

Core Framework: CrewAI

LLM Backend: Gemini

1. Product Overview
Cross-Domain-Creativity-Mapper is a multi-agent CLI application designed to execute advanced lateral thinking and concept mapping. By leveraging CrewAI, the system discovers an obscure or highly unusual phenomenon in a user-defined primary domain and translates its underlying mechanics into a completely unrelated target domain. The system utilizes a five-agent sequential pipeline to output a set of analytical, creative, and commercial Markdown reports detailing the mapping, its real-world feasibility, its narrative potential, and its commercial software applications.

2. User Flow & System Execution
Initialization: The user runs the Python script from the VSCode terminal.

Data Input: The CLI prompts the user to input two variables:

Primary Domain (e.g., Biology, Quantum Physics)

Target Domain (e.g., Politics, Macroeconomics)

Environment Setup: The script automatically generates a target directory for the run: output/[Primary_Domain]_[Target_Domain]/.

Agent Handoff: The CrewAI sequential process initiates, passing context linearly through the five agents.

Output Generation: As tasks complete (or at the end of the sequential run), the system writes the final deliverables as formatted Markdown (.md) files into the generated subfolder.

3. Architecture & Technical Stack
Language: Python 3.10+

Orchestration: CrewAI (Sequential Process model)

LLM Integration: Gemini API (configured via crewai[gemini] or langchain-google-genai). API key managed via .env file.

File System: Native Python os and pathlib libraries for dynamic directory creation and file writing.

4. Agent Definitions & Task Specifications
Agent 1: The Phenomenon Explorer
Role: Deep-dive researcher in the Primary Domain.

Goal: Identify a highly unusual, counter-intuitive, or obscure phenomenon and explain its core mechanisms clearly.

Task: Research the provided Primary Domain. Select a singular, specific, and unexpected phenomenon. Output a detailed summary outlining its rules, causes, and effects.

Agent 2: The Analogical Mapper
Role: Cross-disciplinary systems thinker.

Goal: Translate the mechanisms of the phenomenon directly into the Target Domain, establishing equivalent roles, forces, and outcomes.

Task: Consume Agent 1's output. Map the specific mechanics of the phenomenon to the Target Domain. Output a 1:1 structural analogy, clearly defining the target-domain equivalents for every component of the original phenomenon.

Agent 3: The Analytical Critic
Role: Pragmatic analyst and logic validator.

Goal: Review the mapping for logical consistency, practicality, and real-world feasibility.

Task: Consume Agent 2's mapping. Critique the analogy. Identify where the mapping breaks down, where it reveals surprising practical insights, and evaluate if this mapped concept could exist or be implemented in the real world.

Agent 4: The Narrative Designer
Role: Creative strategist and world-builder.

Goal: Generate compelling narrative frameworks based on the validated concept.

Task: Consume the outputs from Agent 2 and Agent 3. Pitch three distinct narrative concepts (e.g., hard sci-fi, steampunk, alternate history, dystopian thriller) that utilize this mapped phenomenon as a core plot device or world-building element.

Agent 5: The Product Builder
Role: Commercial Product Strategist.

Goal: Generate viable commercial software product concepts based on the cross-domain mapping and its pragmatic critique.

Task: Consume the outputs from Agent 2 and Agent 3. Brainstorm and outline three distinct software applications, SaaS platforms, or commercial tech products that leverage the core mapped mechanics. For each idea, define the target audience, core value proposition, and a basic MVP feature set.

5. Output Specifications
All deliverables must be saved as Markdown files. CrewAI's output_file parameter in the Task definitions will be dynamically routed to the generated directory.