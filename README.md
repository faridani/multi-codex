# multi-codex

multi-codex is a Mac CLI assistant for evaluating multiple AI-generated code branches side by side. Tools like Codex can produce up to four different solutions to the same prompt. multi-codex helps you compare those solutions, pick the best branch, and capture good ideas from the alternatives that are missing in the winner. The typical flow is: ask Codex at `chatgpt.com/codex` to draft four solutions, PR each solution so Codex generates four branches, then run multi-codex to produce an analysis-ready report. The tool deliberately avoids calling the OpenAI API automatically so you can stay within a monthly budget (e.g., skipping the extra $200 plan). It’s especially useful for solo developers juggling many features alone.

## What the tool does

1. **Start `multi-codex`** – A polished CLI greets you and asks for your GitHub repo URL.
2. **Clone with your existing auth** – Accepts SSH or HTTPS URLs, cloning into `~/.multi_codex/repos/<user_repo>` with your Git credentials (works with private repos when `git clone` does).
3. **Monitor branches & attach specs** – Polls `origin` every 30 seconds. When a new branch appears you’re prompted to track it and optionally attach a local specification/requirements document. Press **Enter** to skip a spec; press **Ctrl+C** when you’re ready to analyze.
4. **Generate branch markdown snapshots** – For each selected branch the tool checks out `origin/<branch>`, walks the tree (skipping large/binary files and common build/IDE directories), and writes `branch_<branch_slug>.md` under `~/.multi_codex/reports/<repo_slug>/`.
5. **Produce a combined analysis prompt** – A combined `combined_spec_and_branches.md` includes specs plus branch contents, starting with a system instruction so you can paste it directly into an AI UI for comparison. The CLI can copy the content to your clipboard and gives you a direct link to open ChatGPT for easy pasting.

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
