# A hands-on guide to using multi-codex

Multi-codex is a Mac-friendly CLI companion designed for multi-solution coding workflows. Instead of paying for extra API calls, it works entirely with your local Git clones and GitHub branches, producing shareable Markdown prompts you can paste into your favorite AI UI. This post walks through what it is, what it can do, and how you can use it day-to-day without burning through credits.

## What multi-codex is

Multi-codex watches your GitHub repository for new branches and turns them into AI-ready briefs. The CLI clones your repo (or reuses an existing clone) under `~/.multi_codex/repos/<repo_slug>` and writes reports under `~/.multi_codex/reports/<repo_slug>`. Because it never calls the OpenAI API, you stay in full control of where and how you use your tokens—the tool just gives you rich Markdown files to paste into the UI you already use.

Behind the scenes, the CLI renders a banner, shows an intro panel, and guides you through repository setup and workflow selection (`Architecture`, `Compare`, `PR review`, or `Feature & security`). The workflows rely on `multi_codex/core.py` for git operations, branch syncing, and Markdown generation, and `multi_codex/ui.py` for all of the interactive Rich/typer UI.

## What multi-codex can do

* **Monitor branches and attach specs.** It fetches `origin` every 30 seconds, detects new branches, and lets you queue them for analysis. You can attach a specification by file path or paste it inline when prompted.
* **Snapshot branches into Markdown.** For each selected branch, `collect_branch_markdown` checks out `origin/<branch>`, walks the tree (skipping heavy/binary paths), and renders a project structure plus every text file in fenced code blocks. Each branch snapshot is saved as `branch_<branch_slug>.md` under the reports directory so you can read or share it directly.
* **Assemble comparison prompts.** After gathering specs and branch snapshots, `build_branch_comparison_prompt` creates `combined_spec_and_branches.md`, a single copy-paste prompt that merges your spec and all branch content. The first line uses a system prompt that primes the AI for branch comparison, so you can paste the whole file into chat and ask for the best solution plus borrowable ideas.
* **Generate other long-context prompts.** Additional workflows build architectural reports, PR review mega-prompts (including a diff versus a base branch), and feature/security evaluations—each saved to a dedicated Markdown file and optionally copied to your clipboard.
* **Token-size warnings without API calls.** Before you paste a prompt, `warn_if_large` estimates token counts locally using `tiktoken` and reminds you when you’re above typical 128k windows, again without sending any data to an external API.

## How to use multi-codex to develop code

1. **Install the CLI (Mac).** The repo includes a minimal `pyproject.toml`, so you can install it directly: `python -m pip install --upgrade pip && pip install .`. After that, `multi-codex` is on your `PATH`.
2. **Launch the interactive UI.** Run `multi-codex`. The banner and intro appear, and you’re prompted for your GitHub repository URL (SSH or HTTPS). The tool clones into `~/.multi_codex/repos/<slug>` or reuses your existing clone and fetches latest branches.
3. **Pick a workflow.** Choose `Compare` to evaluate multiple solutions, `Architecture` for a deep architecture brief, `PR review` for long-context review + diff, or `Feature & security` for a targeted audit.
4. **Queue branches and specs.** In the `Compare` flow, the tool monitors `origin` for new branches, asking if you want to add each one to the evaluation lineup. You can attach a spec document by path or paste it inline. Press `Ctrl+C` to stop monitoring and start analysis with the queued branches.
5. **Let it build the Markdown files.** For each branch, the CLI generates a snapshot and saves it to `~/.multi_codex/reports/<repo_slug>/branch_<branch>.md`. It also writes `combined_spec_and_branches.md` that merges your spec and all branches. Other workflows save similarly named files (e.g., `pr_review_prompt_<branch>_vs_<base>.md`).
6. **Paste into your favorite AI UI.** Open any generated Markdown file and paste the entire content into your AI chat window. Since multi-codex never calls the API itself, you only spend tokens when you decide to paste and run the analysis. The `copy_to_clipboard` helper will even copy the prompt automatically when your platform supports it.

### Tips for smooth development

* Keep your branches on `origin`; the tool fetches and checks out `origin/<branch>` for snapshots and diffs.
* Specs are optional—if you skip them, the combined doc notes that no specification was provided.
* Large repos are handled defensively: binary files, very large files (>200KB), and common build/IDE directories are ignored to keep prompts manageable.
* You can rerun workflows anytime; reports are stored under `~/.multi_codex/reports/<repo_slug>` so you can revisit or share them later.

## Why it saves credits

Multi-codex intentionally avoids any OpenAI API calls. Its entire job is to produce rich, contextual Markdown files you can paste into the AI UI you already use. That means your credits are only spent when you decide to run the prompt yourself—no background token burn, no surprise bills. Because each workflow saves the prompt to disk, you can reuse it across assistants (or share it with teammates) without regenerating or re-spending tokens.

Multi-codex is purpose-built for developers juggling multiple solutions: it keeps your comparisons organized, your specs attached, and your AI prompts ready to paste—while keeping your credit usage firmly in your hands.
