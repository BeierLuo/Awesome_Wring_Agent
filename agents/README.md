# Agent rules and project memory

Caret loads its own UTF-8 role and skill files. The writer revises manuscripts, the researcher checks evidence, and the maintainer identifies sections and extracts original text for PDF projects. The stylist analyzes reference papers in batches. Role instructions live in each role's `AGENT.md` file. Task instructions live in `skills/<skill>/SKILL.md`.

Edit the files directly or open the agent rules and memory panel in Caret. New requests read the latest instructions. Requests already running keep their original snapshot. Shared roles and skills apply across projects. Each project's `memory/` directory contains its own `paper.md`, `preferences.md` and `decisions.md`. Users maintain these notes manually. Use the latest manuscript and original sources to verify claims.

Each role loads only its relevant skills. Limits are 12,000 characters per role file, 6,000 per skill file and 2,000 per memory file (6,000 total). Python defines executable tools, budgets, evidence checks and confirmation requirements. The loader treats links, paths and shell commands in Markdown as text. Keep credentials out of these files.

The editor saves previous global rules under `.local/agent-history/` and project memory under `.agent/memory-history/` inside the workspace.

For LaTeX projects, `latex_project.py` splits imported ZIP sources into sections. Caret checks the version and asks for confirmation before applying an edit to the source. The researcher can verify information on demand. PDF section extraction is specific to PDF projects.

For reference papers, `analyze_style` produces examples anchored to the original text. The writer looks up cached examples with `find_style_examples`. Project selections live in `style-reference.json`. The shared library and analysis cache live in `style-library/`.
