# Multi-codex: a practical guide to AI-ready branch comparisons

## What is multi-codex?
Multi-codex is a Mac-first CLI helper that automates multi-branch coding workflows. It watches your GitHub repository, turns branches into neatly formatted markdown snapshots, and builds copy/paste-ready prompts you can drop into your favorite AI UI. The tool never calls the OpenAI API itself, so you avoid burning credits while still getting long-context analysis fuel for ChatGPT or any other assistant.【F:README.md†L5-L26】【F:multi_codex/ui.py†L104-L143】

## What can it do?
Multi-codex offers several interactive workflows right from the terminal banner:

- **Monitor and queue branches**: It fetches `origin` every 30 seconds, spots new branches, and lets you queue the ones you want to evaluate.【F:multi_codex/ui.py†L347-L404】
- **Attach specs or design docs**: Provide a path or paste your spec, and the tool merges it with the branch content so your AI reviewer sees the requirements and the code side by side.【F:multi_codex/ui.py†L294-L341】【F:multi_codex/core.py†L275-L325】
- **Generate branch snapshots**: Each selected branch is checked out, filtered to skip binary/oversized files, and rendered as markdown with a project tree plus file-by-file code fences, then saved under `~/.multi_codex/reports/<repo_slug>/branch_<branch>.md`.【F:multi_codex/core.py†L11-L258】【F:multi_codex/ui.py†L470-L485】
- **Produce ready-to-paste prompts**: Multi-codex builds combined markdown (spec + branches) and specialized prompts for architecture reviews, PR reviews (with diffs), and feature/security assessments, then copies them to your clipboard when possible.【F:multi_codex/core.py†L303-L442】【F:multi_codex/ui.py†L447-L533】
- **Avoid API calls entirely**: All outputs are local markdown files. You can paste them into ChatGPT’s UI (or any assistant) without the tool making network calls to model providers.【F:README.md†L14-L25】【F:multi_codex/ui.py†L104-L143】

## How to use it to develop code

1. **Install once** (Python 3.10+):
   ```bash
   python -m pip install --upgrade pip
   pip install .
   ```
   After installation the `multi-codex` command is on your PATH.【F:README.md†L27-L57】

2. **Launch the CLI**:
   ```bash
   multi-codex
   ```
   The app prints an ASCII banner and walks you through cloning or reusing a local repo under `~/.multi_codex/repos/<slug>`.【F:multi_codex/ui.py†L82-L197】【F:multi_codex/core.py†L83-L118】

3. **Pick a workflow** from the menu:
   - **Compare**: queue branches, attach a spec, and create `combined_spec_and_branches.md` for AI comparison.【F:multi_codex/ui.py†L460-L505】
   - **Architecture**: build a single-branch architecture report prompt.【F:multi_codex/ui.py†L447-L458】
   - **PR review**: capture long-context code plus a diff against a base branch for review prompts.【F:multi_codex/ui.py†L507-L520】
   - **Feature & security**: generate a prompt focused on capabilities and security hardening.【F:multi_codex/ui.py†L522-L533】

4. **Open the saved files** in `~/.multi_codex/reports/<repo_slug>/`. Multi-codex also tries to copy the prompt to your clipboard; if that fails, just open the markdown file and paste it into ChatGPT or any other AI UI.【F:multi_codex/ui.py†L429-L505】

5. **Iterate without burning credits**: Because multi-codex only prepares context and never calls model APIs, you can reuse the saved markdown (especially `combined_spec_and_branches.md`) across multiple AI chats without paying extra for re-uploads. Paste the file into the UI of your choice and let the AI compare branches or draft reviews while you stay within your budget.【F:README.md†L14-L25】【F:multi_codex/ui.py†L493-L505】

## Why this saves AI budget
Every run produces portable markdown you can stash in version control or share with teammates. The branch snapshots and combined prompt files encapsulate the entire code context, so you can repeatedly use them with any assistant UI—even switch providers—without re-ingesting your repo or incurring additional API costs. Multi-codex is a workflow accelerator, not another meter on your bill.【F:README.md†L14-L25】【F:multi_codex/core.py†L275-L325】
