# multi-codex

A Mac CLI tool that watches a GitHub repository for new branches, lets you attach specification documents, and produces OpenAI-powered comparisons of how well each branch satisfies the requirements.

## What the tool does

1. **You run `multi-codex` → CLI appears**: The banner and intro show; it asks for your GitHub repo URL.
2. **GitHub repo address & auth**: Accepts SSH or HTTPS URLs, cloning into `~/.multi_codex/repos/<user_repo>` using your existing Git authentication (works with private repos if `git clone` does).
3. **Monitor branches & attach specs**: Polls `origin` every 30 seconds. When a new branch appears, you’re prompted to add it and optionally provide a path to its specification/requirements document on your Mac. Press **Enter** to skip a spec; press **Ctrl+C** to finish monitoring.
4. **Markdown files per branch + combined doc**: For each selected branch the tool checks out `origin/<branch>`, walks the tree (ignoring large/binary files and common build/IDE directories), and writes `branch_<branch_slug>.md` under `~/.multi_codex/reports/<repo_slug>/`. A combined doc with all specs and branch contents is saved as `combined_spec_and_branches.md`.
5. **OpenAI API analysis & comparison table**: Sends the combined markdown to OpenAI (`gpt-4o` by default) to infer key features from the specs, build a Yes/No feature vs. branch table, pick the best branch, and list missing/partial features. The report is saved to `openai_branch_comparison_report.md` alongside the other outputs.

## How to run it as `multi-codex` on macOS

### Install as a Python console script (recommended)

The repository already includes a minimal `pyproject.toml`, so you can install and run the tool directly:

```bash
pip install .
```

After installation, `multi-codex` is available on your PATH. Use it in any directory with:

```bash
multi-codex
```

## Environment setup

```bash
# 1. Install the tool (includes dependencies)
pip install .

# 2. Set your API key (bash/zsh)
export OPENAI_API_KEY="sk-..."

# 3. Run
multi-codex
```
