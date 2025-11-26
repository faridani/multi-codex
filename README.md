# multi-codex

multi-codex is the command-line companion for reviewing multiple AI-generated solutions side by side. Tools like Codex can produce up to four different solutions to the same prompt; multi-codex helps you compare them, decide which one is best, and still capture the good ideas hiding in the other branches. The typical workflow:

1. Ask Codex (e.g., at `chatgpt.com/codex`) to produce four solutions and open pull requests for each, giving you four branches.
2. Run multi-codex to watch the repository, pick the branches to evaluate, and attach any specs or design docs.
3. Read the generated report that spotlights the strongest branch plus the valuable ideas it missed.

By design, multi-codex never calls the OpenAI API for you—you stay in control of costs instead of burning through an extra $200/month. It’s a practical helper for solo developers who juggle lots of feature development and want a calm, repeatable way to pick the right branch.

A Mac CLI tool that watches a GitHub repository for new branches, lets you attach specification documents, and produces a single combined prompt you can paste into your AI UI to compare how well each branch satisfies the requirements.
## What the tool does

1. **You run `multi-codex` → CLI appears**: The banner and intro show; it asks for your GitHub repo URL.
2. **GitHub repo address & auth**: Accepts SSH or HTTPS URLs, cloning into `~/.multi_codex/repos/<user_repo>` using your existing Git authentication (works with private repos if `git clone` does).
3. **Monitor branches & attach specs**: Polls `origin` every 30 seconds. When a new branch appears, you’re prompted to add it and optionally provide a path to its specification/requirements document on your Mac. Press **Enter** to skip a spec; press **Ctrl+C** to finish monitoring.
4. **Markdown files per branch + combined doc**: For each selected branch the tool checks out `origin/<branch>`, walks the tree (ignoring large/binary files and common build/IDE directories), and writes `branch_<branch_slug>.md` under `~/.multi_codex/reports/<repo_slug>/`. A combined doc with all specs and branch contents is saved as `combined_spec_and_branches.md`. Its first line is `You are an expert software architect.` so you can copy the whole file directly into your AI chat UI to get the detailed comparison.

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
# Install the tool (includes dependencies)
pip install .

# Run
multi-codex
```
