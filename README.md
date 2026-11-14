# Caret · A local workspace for research writing

[中文 README](README.zh-CN.md)

Import a PDF or LaTeX project, choose a section, and ask Caret to revise it. Review the proposed text alongside the manuscript and save the changes you want. Caret keeps the section history, conversations and project files on your computer. Gemini or OpenAI handles writing, and an OpenAI research assistant can look up evidence, read PDF pages and analyze reference papers.

[Download Caret for Apple Silicon Macs](https://github.com/BeierLuo/Awesome_Wring_Agent/releases/latest) · [Changelog](CHANGELOG.md) · [Development conventions](AGENTS.md)

## Run from source

Use Python 3.10 or later. From the project directory, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

On macOS, after installing the dependencies, you can also double-click `Launch Caret.command` to start the workspace.

On Windows, use `.venv\Scripts\python.exe` for the installation and server commands. Open <http://127.0.0.1:8768/en/> for English or <http://127.0.0.1:8768/> for the default interface. The language switch shares projects and settings across both views and preserves the language of your text.

The server listens on the loopback interface. Use `python server.py --port 8769 --no-open` to choose a port and skip opening the browser. Use `--root /path/to/private-workspaces` to move manuscript workspaces. API settings and the shared reference library still use the application directory.

### Connect a model

Open **API Settings**. For Gemini writing, choose Vertex AI (Express Key, standard project key or Application Default Credentials) or the Gemini Developer API. For ADC, install the Google Cloud CLI and run `gcloud auth application-default login`. Set the model, project and region to values your account can access.

For OpenAI writing, choose **OpenAI API**, enter your key and set the writing model ID. Leaving it blank uses the research assistant model. The writer needs Responses API, tool calling and image input support. PDF section processing, reference analysis and research use the separate OpenAI assistant configuration.

Credentials are stored in `.local/api-config.json` with file mode 600 and directory mode 700. Model calls send the relevant passages, reference excerpts or page images to your provider and incur provider charges. Reference analysis sends extractable text in batches.

## Write and review

1. Create a project and import a PDF or a LaTeX ZIP. For a PDF, wait for section detection and extraction. Scans may need an OCR text layer. LaTeX projects derive sections from source files. Complex macros or dynamic includes may need manual adjustment.
2. Choose a section and describe the change. The writer can request evidence with sources, read the latest section or inspect specific PDF pages. Use Enter for a newline and ⌘Enter, Ctrl+Enter or the send button to submit.
3. Review the proposed edit and accept it to create a section version. For local LaTeX edits, Caret checks the source version, unique text matches and non-overlapping replacements before writing. Explicit whole-section rewrites and older full-section suggestions are also supported.
4. Continue the conversation, switch sessions, inspect versions or export the project. Switching sessions preserves pending input. The project list supports search, renaming, trash and restore.

The model menu applies to the next message and locks during generation. Add alternate model IDs in API Settings, separated by commas. The stop button interrupts generation. Reasoning effort is remembered per model. Supported OpenAI and Gemini models offer default, low, medium and high settings.

### Edit LaTeX alongside the PDF

Use the chapter list on the left, Assistant or Source in the middle and the compiled PDF on the right. Save your source and choose **Recompile**, or press ⌘S to save and compile. A successful build refreshes the current page. A failed build leaves the last successful PDF visible. You can scroll, jump to a page, zoom, fit the page or width, and drag the divider. Narrow windows stack the editor above the preview. Drag the handle above the message box to resize it or double-click to reset.

On macOS, install Tectonic on your PATH or place a compatible executable at `.tools/tectonic`. The first build may download TeX packages. Projects requiring LuaLaTeX, external scripts or other tools may need a different compiler. Other platforms support editing and ZIP export.

Double-click text in a freshly compiled PDF to jump to the source line, including in files loaded with `\input`. Recompile older projects to generate SyncTeX data. Formulas, macros and figures may map to a nearby command. Drag to select or copy embedded text. To revise a paragraph, select text and choose the paragraph-edit action. Inspect the selected TeX above the message box. Caret keeps the selection per chapter across messages and reloads, highlights it in the preview, and follows it after accepted edits and recompilation. Selections can span pages within one file and chapter. If external edits make the range ambiguous, select it again.

Use the PDF location action to reveal the imported `workspaces/<project-id>/original.pdf` or last compiled `.latex/compiled.pdf` in your file manager.

### Use references and writing preferences

Import papers into the reference library to analyze style, find examples and generate section strategies. The library starts empty. Search by title, abbreviation, author or year and ask the assistant to read a section directly from a reference paper. To confirm a chapter type independently, select the chapter, open the writing strategy panel in project settings, choose a type such as Motivation and confirm it. Enable the strategy to use that type for rule and example retrieval.

Open **Writing Preferences** above the conversation to manage rules for all writing, a chapter type, a paper or a single chapter. Each reply shows the preference version and rules it used. When chat learning is enabled, a successful turn with a preference signal may trigger an additional model call. Explicit long-term requests can be recorded automatically. Inferences, changes to existing rules and author-style suggestions require review. Author-style suggestions must cite a locally verified passage. You can edit, accept or reject a suggestion or disable learning. Closing Caret may interrupt analysis. Failed analysis preserves the reply and existing preferences.

The local Git repository under `.local/preferences/` records who changed each rule, its source and the reason. Compare versions, mark a preferred version or restore one rule or the whole set. Each restore creates a new commit. Existing project memory in `memory/preferences.md` and earlier author notes remain available.

### Sync with Overleaf

Open **Overleaf Sync** beside Assistant / Source in a local LaTeX project. Enter the Overleaf Cloud project or Git URL and a Git access token from an account with Git integration. Preview incoming or outgoing changes before applying them, including on the first sync. For files edited on both sides, choose the full local or remote file after inspecting the diff excerpt. Preview again if either side changes.

Sync covers supported manuscript sources and assets under `latex/`. It preserves local-only edits on pull, retains matching chapter histories, archives removed chapters locally and leaves unsupported remote files in place. Recompile to refresh the PDF. Sync operates on files and excludes Overleaf comments and tracked changes.

Connection details are user-readable only in `.local/overleaf/<workspace-id>/connection.json`. Disconnecting removes the local token. Revoke it separately in Overleaf if needed. Source backups are under `.latex/history/overleaf-*`. Conversations, memory, API settings and build logs stay local.

### Remote workspace

The separate private Sites project in `sites/draft-remote/` uses the local interface. Start the Mac bridge with `.venv/bin/python remote_bridge.py`. The Mac collects requests, processes them locally and returns the results. Sites temporarily holds requests and responses. A remote save requires the Mac to be online. API settings are read-only remotely. Each request is limited to 16 MB, so import large projects locally first. Bridge settings use `.local/sites-bridge.json` with mode 600.

## macOS application

The DMG targets Apple Silicon and requires a separately prepared Python runtime and LaTeX tools. The app uses an ad hoc signature and has not been notarized by Apple. To prepare the current Mac from an existing source environment and create a development build, run:

```bash
.venv/bin/python macos/install_environment.py
.venv/bin/python macos/build.py
```

The setup script copies existing data and refuses to overwrite an existing destination. Under `~/Library/Application Support/Draft/`, `runtime/` holds Python and its dependencies, `tools/` holds LaTeX tools and caches, and `data/` holds papers, references, rules and settings. Continue writing in the new copy after migration. The Caret menu opens its data folder. The name of this folder and the bundle ID preserve compatibility with Draft.

Drag Caret.app from the disk image into Applications. The app uses local port 18768 when available and otherwise selects a free port. Closing the window leaves Caret in the Dock. Save and wait for generation or compilation to finish before quitting with ⌘Q. Startup logs are in `data/.local/mac-app.log`. Building requires Apple Command Line Tools.

## Development and local data

The browser interface lives in `ui/` and runs without a frontend build step. `server.py` serves the UI and project API. `writing_agent.py` coordinates the LangGraph workflow. Research tools live in `paper_assistant.py` and `paper_tools.py`, streaming in `gemini_stream.py`, LaTeX handling in `latex_project.py`, and project management in `projects.py`. The reference library and writing strategy use `style_library.py` and `style_memory.py`. Edit shared roles in `agents/` and task instructions in `skills/`.

The Git allowlist covers reviewed source, assets, rules, tests and documentation. Keep credentials, papers, conversations and personal rules out of shared files. Local paths include `.local/` (settings and history), `workspaces/` (papers and versions), `style-library/` (reference papers and style memory), `work/` (working files), and `.venv/`, `.python/` and `.tools/` (runtimes and caches). Review staged changes with `git diff --cached`. If credentials were exposed, revoke and replace them before cleaning history.

Run the Python and JavaScript checks from the project root:

```bash
python -m unittest discover -s tests -v
node tests/test_ui.cjs
npm ci --prefix tests --ignore-scripts
node tests/test_markdown.cjs
```

Model tests use mock responses. Verify live provider access separately in settings.

### Builds and releases

Use `python macos/build.py --plan` to inspect a build. The default build writes Caret.app and Caret.dmg under `dist/tmp/` using the current version. Verify it with `python macos/check_installation.py`. Accumulate changes there until a release is explicitly requested. For an approved release, run `python macos/build.py --release --version X.Y.Z` and `python macos/check_installation.py --release`. Installation is a separate step.

After successful release validation, the cleanup tool archives redundant app copies that match the installed release. It preserves running apps, unpublished builds, the release DMG and the three most recent rollback archives. Use `python3 macos/cleanup_releases.py` to preview cleanup and add `--apply` to execute it. Manuscript versions and preference history are recorded independently of application releases.
