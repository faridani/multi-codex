# Building faster with multi-codex: a practical guide

Multi-codex is a macOS command-line sidekick for multi-branch solution workflows. It watches your GitHub repository, snapshots code from any branches you pick, and packages everything into prompts you can paste into your favorite AI UI without triggering extra API spend. This post walks through what the tool is, what it does, and how you can use it to ship code faster.

## What is multi-codex?

Multi-codex is designed for the common “ask an AI for several approaches, then pick the best” loop. You create a few branches (often produced by Codex or ChatGPT), and multi-codex gathers them into a single, AI-ready report so you can compare solutions side by side. Crucially, the CLI never calls the OpenAI API itself—it only prepares files you can feed into the UI you already use, so you avoid burning through metered tokens or monthly credits.【F:README.md†L8-L26】【F:multi_codex/ui.py†L104-L143】

## What can it do?

Multi-codex wraps several workflows that revolve around branch-aware analysis:

- **Monitor branches and capture specs.** The CLI polls `origin` every 30 seconds, lets you queue new branches as they appear, and asks for an optional spec file or pasted requirements to include in the comparison.【F:README.md†L22-L25】【F:multi_codex/ui.py†L294-L405】
- **Generate full-branch snapshots.** For each selected branch, the tool checks it out, walks the tree (skipping binary/large files and build artifacts), and writes a Markdown snapshot plus a project tree to `~/.multi_codex/reports/<repo>/branch_<slug>.md`.【F:multi_codex/core.py†L11-L258】【F:multi_codex/ui.py†L470-L483】
- **Assemble ready-to-paste prompts.** Whether you’re comparing branches, preparing a PR review, or running architecture/security passes, multi-codex stitches the snapshots (and diffs, when needed) into formatted prompts and saves them alongside token estimates. It will even copy them to your clipboard when possible so you can paste directly into the AI chat UI.【F:multi_codex/core.py†L260-L432】【F:multi_codex/ui.py†L429-L533】
- **Offer multiple workflows from one menu.** The interactive launcher provides Architecture, Compare, PR review, and Feature & security flows right after connecting to your repo, so you can pick the lens you need for a branch.【F:multi_codex/ui.py†L575-L624】

## How to use it to develop code

1. **Install the CLI.** From the repo root, install the console script via pip; `multi-codex` will land on your PATH.【F:README.md†L31-L57】
2. **Run `multi-codex` and connect to a repo.** The launcher greets you with a banner and cloning helper. It reuses your existing Git auth, cloning into `~/.multi_codex/repos/<repo_slug>` if needed.【F:README.md†L22-L24】【F:multi_codex/ui.py†L145-L197】
3. **Pick a workflow.** Choose Compare to consolidate multiple feature branches, Architecture for a focused design read, PR review to bundle a long-context snapshot plus diff, or Feature & security for modernization and risk checks.【F:multi_codex/ui.py†L575-L624】
4. **Queue branches and add specs.** In Compare mode, multi-codex monitors your remote branches and prompts you to add newcomers to the lineup. You can attach a spec file or paste requirements before analysis begins.【F:multi_codex/ui.py†L294-L405】【F:multi_codex/ui.py†L460-L505】
5. **Open the generated files.** Each branch snapshot and the combined prompt are written under `~/.multi_codex/reports/<repo>/`. The CLI also shows token estimates so you can decide whether to trim context before pasting into your AI tool.【F:multi_codex/core.py†L206-L325】【F:multi_codex/ui.py†L429-L505】

## Save credits by pasting, not paying

Because multi-codex only reads your code and writes Markdown, you’re free to open the saved prompt files in your editor and paste them into chatgpt.com (or any other AI UI) without any API calls from the tool. The combined comparison document includes the spec plus every branch’s contents, so you get rich guidance without spending extra tokens directly from the CLI.【F:README.md†L14-L26】【F:multi_codex/ui.py†L493-L505】

## Final thoughts

Multi-codex streamlines the messy middle of multi-solution development: it keeps an eye on your branches, packages them into clear prompts, and leaves you in control of when and where to run the analysis. That means less time wrangling diffs, more time shipping the strongest ideas—without surprise API bills.
