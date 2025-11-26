# multi-codex

multi-codex is a GitHub branch comparison companion for solo developers who juggle multiple feature experiments. Tools like Codex can produce up to four different solutions; multi-codex helps you compare them, decide which branch is best, and surface good ideas from the alternatives that the best solution might be missing. Because it never calls the OpenAI API automatically, you avoid surprise charges on top of your monthly budget.

## How it works

1. **Ask Codex for four solutions**: Use `chatgpt.com/codex` to generate four approaches to your feature. PR each solution so Codex creates four branches.
2. **Run multi-codex**: Point the CLI at your repository and provide the spec. The tool watches for branches, collects their file contents (skipping bulky or binary assets), and turns each branch into a markdown snapshot.
3. **Compare effortlessly**: multi-codex builds a combined markdown file containing your spec plus every selected branch. Paste it into your AI UI to get a concise comparison table and a summary of what the best branch still lacks.

## Why you'll like it

- **Budget-friendly**: No automatic OpenAI API calls—everything stays local until you decide to query an AI.
- **Idea harvesting**: Highlights ideas implemented in alternate branches that the winning branch missed.
- **Solo-dev ready**: Lets you manage multiple feature branches without losing track of which experiments cover which requirements.

## Running the CLI

### Install as a Python console script (recommended)

The repository includes a minimal `pyproject.toml`, so you can install and run the tool directly:

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
