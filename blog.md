# Building With Multi-codex: A Practical Guide

Multi-codex is a macOS-friendly CLI companion for multi-solution coding workflows. Instead of asking your AI assistant to churn through every branch directly (and burn through credits), multi-codex prepares rich markdown packages you can paste into any UI—ChatGPT, Claude, or your favorite tool. Everything is grounded in your repository and never calls the OpenAI API, so you stay in control of both context and cost.

## What Multi-codex Is

At its core, multi-codex is a branch evaluator for GitHub repositories. When you point it at a repo, it will:

- Clone (or reuse) the repository under `~/.multi_codex/repos/` and set up matching report folders under `~/.multi_codex/reports/` via `ensure_app_dirs` in `core.py`.
- Watch `origin` for branches, let you pick which ones to analyze, and optionally attach a spec/design doc.
- Build markdown snapshots for each branch—complete with a project tree and code blocks for every relevant file—so you can drop them into your AI chat.
- Assemble higher-level prompts (architecture review, branch comparison, PR review, feature/security scan) by combining system prompts with the collected markdown.

## What Multi-codex Can Do

Multi-codex ships four workflows exposed in the interactive menu:

1. **Architecture report** – captures a full branch snapshot and wraps it with the architecture prompt from `prompts/architecture_report.md`. (`run_architecture` → `build_architecture_report`)
2. **Compare branches** – monitors for new branches, gathers branch markdown, folds in your spec, and produces a single comparison prompt based on `prompts/branch_comparison.md`. (`run_compare` → `build_branch_comparison_prompt`)
3. **PR review** – prepares a “mega prompt” that includes long-context branch content plus a git diff against your chosen base branch. (`run_pr_review` → `build_pr_mega_prompt`)
4. **Feature & security** – snapshots a branch and applies the feature/security modernization prompt. (`run_feature_security` → `build_feature_security_report`)

These options are defined in the interactive menu setup in `ui.py`, so you pick one after connecting to your repo.

## How Multi-codex Works Under the Hood

### Cloning and Monitoring

- When you enter a GitHub URL, `prepare_repository` slugifies the URL, creates per-repo directories, and clones if needed. (`slugify_repo_url`, `ensure_local_clone`)
- The branch comparison flow launches `monitor_branches`, which polls `origin` every 30 seconds. New branches trigger a prompt asking whether to add them to the evaluation set.

### Building Branch Snapshots

- `collect_branch_markdown` checks out each branch locally, walks the tree while skipping noisy folders (e.g., `.git`, `node_modules`, build artifacts), and ignores binary or oversized files. It builds an ASCII project tree and embeds each file’s content in fenced code blocks with language hints. This produces the branch `<name>.md` reports saved under `~/.multi_codex/reports/<repo>/`.

### Prompt Assembly

- For comparisons, `build_branch_comparison_prompt` merges your spec (path or pasted content) plus all selected branch markdown into one document headed by the branch-comparison system prompt. The result is a copy-paste-ready markdown file named `combined_spec_and_branches.md`.
- The PR review workflow uses `build_pr_mega_prompt` to include both long-context markdown and a git diff (`git diff origin/<branch>...origin/<base>`). Diff failures are reported inline as text blocks so your AI assistant sees the error context.
- All workflows estimate token counts with `warn_if_large` and try to copy the prompt to your clipboard. If the clipboard step fails, you can open the saved markdown file directly.

## Using Multi-codex to Develop Code

1. **Install and launch**
   ```bash
   python -m pip install --upgrade pip
   pip install .
   multi-codex
   ```
2. **Connect to your repo** – paste the HTTPS/SSH URL when prompted. The tool fetches `origin` and shows an action menu.
3. **Pick a workflow** – choose architecture, compare, PR review, or feature/security. For branch comparisons, paste or point to your spec document and let the monitor collect branches.
4. **Review the generated files** – every workflow writes markdown files under `~/.multi_codex/reports/<repo_slug>/`. Open them in your editor or copy them into your AI UI.
5. **Iterate without burning credits** – since multi-codex never calls the API, you can reuse the generated markdown across tools. Paste the branch snapshots or combined prompts into the UI of your preferred assistant to get insights without extra API spend.

## Why This Saves Credits

Multi-codex does the expensive context-wrangling locally: it clones your repo, captures full code snapshots, and assembles prompts offline. You then paste those ready-to-use markdown files into whichever AI UI you prefer. Because multi-codex itself never makes API calls, you avoid surprise usage and can reuse the same prompt file multiple times across assistants.

## Tips for Effective Use

- Trim large binaries or build artifacts: the collector skips common noise, but keeping your repo clean improves token counts.
- For comparisons, include a concise spec so the branch-comparison prompt can score features accurately.
- Use the PR review workflow when you want both the full branch context and an explicit diff against your base branch.

Happy branching—let multi-codex handle the paperwork while you focus on choosing (and improving) the best solution.
