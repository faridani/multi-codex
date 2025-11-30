from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

import tiktoken
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from . import core

POLL_INTERVAL_SECONDS = 30
CONTEXT_LIMIT_TOKENS = 128_000

console = Console()
app = typer.Typer(add_completion=False)

BANNER = r"""
░███     ░███            ░██    ░██    ░██                             ░██
░████   ░████            ░██    ░██                                    ░██
░██░██ ░██░██ ░██    ░██ ░██ ░████████ ░██ ░███████   ░███████   ░████████  ░███████  ░██    ░██
░██ ░████ ░██ ░██    ░██ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██  ░██  ░██
░██  ░██  ░██ ░██    ░██ ░██    ░██    ░██░██        ░██    ░██ ░██    ░██ ░█████████   ░█████
░██       ░██ ░██   ░███ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██   ░███ ░██         ░██  ░██
░██       ░██  ░█████░██ ░██     ░████ ░██ ░███████   ░███████   ░█████░██  ░███████  ░██    ░██




Multi-branch solution evaluator for GitHub repos.
"""


@dataclass
class BranchSpec:
    """Holds info about a tracked branch."""

    name: str
    branch_markdown_path: Optional[Path] = None


class Workflow(str, Enum):
    ARCHITECTURE = "architecture"
    COMPARE = "compare"
    PR_REVIEW = "pr-review"
    FEATURE_SECURITY = "feature-security"


def print_banner() -> None:
    console.print(Markdown(f"```\n{BANNER}\n```"), style="cyan")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    return typer.confirm(prompt, default=default)


def ensure_local_clone(repo_url: str, repo_path: Path) -> None:
    if (repo_path / ".git").is_dir():
        console.print(f"[green]Using existing local clone at:[/] {repo_path}")
        with console.status("Fetching latest changes from origin..."):
            core.run_git(repo_path, ["fetch", "origin", "--prune"])
        return

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]\nCloning repository into:[/] {repo_path}")
    cmd = ["git", "clone", repo_url, str(repo_path)]

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Cloning repository...", start=False)
            progress.start_task(task_id)
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            progress.update(task_id, completed=1, description="Repository cloned")
    except FileNotFoundError:
        console.print("[red]Error: 'git' command not found. Please install Git and try again.[/]")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as e:
        console.print("\n[red]Git clone failed.[/]")
        if e.stderr:
            console.print(Markdown(f"```\n{e.stderr}\n```"))
        raise typer.Exit(code=1)


def select_branch(branches: List[str], prompt: str) -> Optional[str]:
    if not branches:
        raise ValueError("No branches available for selection")

    while True:
        console.print(prompt)
        for idx, branch in enumerate(branches, 1):
            console.print(f"  {idx}. {branch}")

        choice = console.input("Select a branch by number or name (or press Enter to cancel): ").strip()
        if not choice:
            return None

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(branches):
                return branches[idx - 1]
            console.print("[yellow]Invalid branch number. Please choose a listed option.\n[/]")
            continue

        if choice in branches:
            return choice

        console.print("[yellow]Branch not recognized. Enter a listed number or an exact branch name.\n[/]")


def prompt_for_branch_selection(repo_path: Path, action_label: str) -> str:
    with console.status("Refreshing branch list..."):
        core.run_git(repo_path, ["fetch", "origin", "--prune"])
    branches = sorted(core.get_remote_branch_names(repo_path))

    if not branches:
        console.print("[red]No remote branches found on origin. Exiting.[/]")
        raise typer.Exit(code=1)

    choice = select_branch(branches, f"Select the branch to {action_label}:")
    if choice is None:
        console.print("[yellow]No branch selected. Exiting.[/]")
        raise typer.Exit(code=1)

    return choice


def prompt_for_project_spec() -> tuple[Optional[str], str]:
    console.print("\nProvide the specification/design document for this project.")
    console.print("Option 1: enter a file path.")
    console.print("Option 2: press Enter and paste the spec content (finish with a line containing only 'EOF').\n")

    while True:
        raw = typer.prompt("Path to spec document (or press Enter to paste it now)", default="").strip()
        if raw:
            expanded = os.path.expanduser(raw)
            if not os.path.isfile(expanded):
                console.print("[yellow]That file does not exist. Please try again.\n[/]")
                continue

            try:
                with open(expanded, "r", encoding="utf-8") as f:
                    content = f.read()
                return expanded, content
            except UnicodeDecodeError:
                with open(expanded, "r", encoding="latin-1") as f:
                    content = f.read()
                return expanded, content
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]Error reading spec file: {e}\n[/]")
                continue

        console.print("\nPaste the specification content. End input with a single line containing only 'EOF'.")
        lines: List[str] = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "EOF":
                break
            lines.append(line)

        content = "\n".join(lines).strip()
        if not content:
            console.print("[yellow]No specification content provided. Please provide a path or paste content.\n[/]")
            continue

        return None, content


def copy_to_clipboard(text: str) -> bool:
    platform = sys.platform

    if platform == "darwin":
        if shutil.which("pbcopy") is None:
            return False
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    if platform.startswith("win"):
        if shutil.which("clip") is None:
            return False
        try:
            subprocess.run(["clip"], input=text, text=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    if platform.startswith("linux"):
        if shutil.which("wl-copy") is not None:
            try:
                subprocess.run(["wl-copy"], input=text, text=True, check=True)
                return True
            except subprocess.CalledProcessError:
                return False

        if shutil.which("xclip") is not None:
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
                return True
            except subprocess.CalledProcessError:
                return False

    return False


def print_saved_file(label: str, path: Path) -> None:
    console.print(f"{label}: [blue]{path}[/]")


async def monitor_branches(repo_path: Path, poll_interval: int = POLL_INTERVAL_SECONDS) -> Dict[str, BranchSpec]:
    selected: Dict[str, BranchSpec] = {}
    seen_branches: Set[str] = set()

    console.print("[cyan]\nMonitoring origin for fresh branches...[/]", style="bold")
    console.print(
        "[grey]When a branch ships, you'll decide whether to add it to the evaluation queue.[/]")
    console.print(
        "[grey]Start analysis at any time or keep watching for more contenders. Press Ctrl+C when you're ready to switch to analysis.\n[/]"
    )

    try:
        while True:
            try:
                with console.status("Fetching updates from origin..."):
                    await asyncio.to_thread(core.run_git, repo_path, ["fetch", "origin", "--prune"])
            except Exception:
                await asyncio.sleep(poll_interval)
                continue

            remote_branches = await asyncio.to_thread(core.get_remote_branch_names, repo_path)
            new_branches = sorted(remote_branches - seen_branches)

            for branch in new_branches:
                console.print(f"[green]●[/] [magenta bold]New branch detected:[/] [grey]{branch}[/]")
                add_prompt = f"Add '{branch}' to the evaluation lineup?"
                if ask_yes_no(add_prompt, default=True):
                    selected[branch] = BranchSpec(name=branch)
                    console.print(f"[green]Branch '{branch}' added to the evaluation set.\n[/]")

                    start_now = ask_yes_no(
                        "Start analysis now? (Otherwise I'll keep monitoring for more branches.)",
                        default=False,
                    )
                    if start_now:
                        console.print("[cyan]\nStarting analysis with the current set of branches...\n[/]", style="bold")
                        return selected
                else:
                    console.print(f"[yellow]Skipping branch '{branch}'.[/]")
                    start_prompt = "Start analysis now with the branches already queued?"
                    if not selected:
                        start_prompt = (
                            "Start analysis now even though no branches are queued yet? (You can always resume monitoring.)"
                        )

                    if ask_yes_no(start_prompt, default=False):
                        console.print("[cyan]\nLaunching analysis with the current lineup...\n[/]", style="bold")
                        return selected

            seen_branches = remote_branches

            if selected:
                tracked = ", ".join(sorted(selected.keys()))
                console.print(f"[grey]Currently tracking branches: {tracked}[/]")

            await asyncio.sleep(poll_interval)

    except KeyboardInterrupt:
        console.print("\n\n[cyan]Stopping branch monitor and moving on to analysis...\n[/]")

    return selected


def estimate_token_count(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def warn_if_context_exceeded(label: str, prompt_body: str, limit: int = CONTEXT_LIMIT_TOKENS) -> None:
    tokens = estimate_token_count(prompt_body)
    if tokens > limit:
        console.print(
            f"[yellow]Warning:[/] {label} is approximately {tokens:,} tokens, exceeding the standard {limit:,}-token context window."
        )
    else:
        console.print(f"[green]Estimated token count for {label}: {tokens:,}[/]")


def _render_intro() -> None:
    intro = textwrap.dedent(
        """
        Multi-codex is your branch evaluator for Codex-style multi-solution workflows.
        Ask Codex for up to four different solutions, push each as its own branch, and let multi-codex
        gather them into a single, AI-ready brief. It highlights what each branch does well and what
        the winning branch should borrow from the others—all without calling the OpenAI API or adding
        surprise costs.
        """
    ).strip()

    console.print(Markdown(intro))

    table = Table(title="What I will do for you", show_header=False, box=None)
    steps = [
        "Monitor your GitHub repository for new branches in real time.",
        "Guide you through selecting the branches and attaching your spec or design doc.",
        "Generate rich markdown snapshots for every branch you pick.",
        "Assemble polished prompts you can paste straight into your AI UI for analysis and comparison.",
    ]

    for idx, step in enumerate(steps, 1):
        table.add_row(f"[green]{idx}[/]", step)

    console.print(table)
    console.print()


@app.command()
def run(
    repo_url: str = typer.Option(
        None,
        prompt="Enter your GitHub repository URL (HTTPS or SSH)",
        help="URL of the repository to analyze.",
    ),
    workflow: Workflow = typer.Option(
        None,
        "--workflow",
        "-w",
        prompt="Select the workflow you want to run",
        help="Choose which prompt to generate.",
    ),
    poll_interval: int = typer.Option(
        POLL_INTERVAL_SECONDS,
        "--poll-interval",
        min=5,
        help="Seconds between remote branch checks when monitoring.",
    ),
) -> None:
    print_banner()
    _render_intro()

    repo_slug = core.slugify_repo_url(repo_url)
    repo_path, report_path = core.ensure_app_dirs(repo_slug)

    ensure_local_clone(repo_url, repo_path)

    if workflow is Workflow.ARCHITECTURE:
        branch_name = prompt_for_branch_selection(repo_path, "analyze for architecture")
        console.print(f"\nPreparing architectural report prompt for branch: [blue]{branch_name}[/]\n")
        combined_prompt = core.build_architecture_report(repo_path, branch_name)

        branch_slug = core.slugify_branch_name(branch_name)
        output_path = report_path / f"architecture_report_{branch_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("Architectural report prompt saved to", output_path)
        warn_if_context_exceeded("architectural report", combined_prompt)
        if copy_to_clipboard(combined_prompt):
            console.print(
                "  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.",
                style="green",
            )
        else:
            console.print(
                "  • Copy the report from the path above to share with your AI assistant.",
                style="yellow",
            )

    elif workflow is Workflow.COMPARE:
        spec_path, spec_content = prompt_for_project_spec()

        branch_specs = asyncio.run(monitor_branches(repo_path, poll_interval=poll_interval))

        if not branch_specs:
            console.print("[yellow]No branches were selected for evaluation. Exiting.[/]")
            raise typer.Exit(code=1)

        console.print("Generating markdown snapshot for each selected branch...\n")
        branch_markdown: Dict[str, str] = {}

        for branch_name, bs in branch_specs.items():
            console.print(f"Processing branch: [blue]{branch_name}[/]")
            md_text = core.collect_branch_markdown(repo_path, branch_name)
            branch_markdown[branch_name] = md_text

            branch_slug = core.slugify_branch_name(branch_name)
            branch_md_path = report_path / f"branch_{branch_slug}.md"
            branch_md_path.write_text(md_text, encoding="utf-8")
            bs.branch_markdown_path = branch_md_path
            print_saved_file("  -> Branch markdown saved to", branch_md_path)

        combined_prompt = core.build_branch_comparison_prompt(spec_path, spec_content, branch_markdown)
        combined_prompt_path = report_path / "combined_spec_and_branches.md"

        combined_prompt_path.write_text(combined_prompt, encoding="utf-8")

        console.print("\n[magenta bold]Combined markdown saved to:[/]")
        print_saved_file("  -> Path", combined_prompt_path)
        console.print("  (Contents intentionally not printed to avoid console noise)\n")

        copied = copy_to_clipboard(combined_prompt)
        warn_if_context_exceeded("combined comparison prompt", combined_prompt)
        console.print("[magenta bold]Next step: share with ChatGPT.[/]")
        if copied:
            console.print("  • Combined prompt copied to your clipboard.", style="green")
        else:
            console.print("  • Copy the combined prompt file to your clipboard from the path above.", style="yellow")
        console.print(
            "  • Open https://chatgpt.com/ and paste the contents into the UI to run the branch analysis.",
            style="grey",
        )

        console.print("\n[green bold]Done ✅[/]")
        console.print("[grey]You can open the markdown files in your editor to inspect:[/]")
        print_saved_file("  - Combined specs + branches prompt", combined_prompt_path)
        console.print("\n[cyan]Thank you for using multi-codex.\n[/]", style="bold")

    elif workflow is Workflow.PR_REVIEW:
        branch_name = prompt_for_branch_selection(repo_path, "convert to long context and diff for PR review")
        base_branch_input = typer.prompt("Enter the base branch to diff against", default="main").strip()
        base_branch = base_branch_input or "main"

        console.print(f"\nBuilding long-context snapshot for PR branch: [blue]{branch_name}[/]\n")
        combined_prompt = core.build_pr_mega_prompt(repo_path, branch_name, base_branch)

        branch_slug = core.slugify_branch_name(branch_name)
        base_slug = core.slugify_branch_name(base_branch)
        output_path = report_path / f"pr_review_prompt_{branch_slug}_vs_{base_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("PR review mega prompt saved to", output_path)
        warn_if_context_exceeded("PR review mega prompt", combined_prompt)
        if copy_to_clipboard(combined_prompt):
            console.print("  • PR mega prompt copied to your clipboard.", style="green")
        else:
            console.print(
                "  • Copy the PR mega prompt from the path above to share with your AI assistant.",
                style="yellow",
            )

    else:
        branch_name = prompt_for_branch_selection(repo_path, "analyze for features and security")
        console.print(f"\nPreparing feature and security analysis for branch: [blue]{branch_name}[/]\n")
        combined_prompt = core.build_feature_security_report(repo_path, branch_name)

        branch_slug = core.slugify_branch_name(branch_name)
        output_path = report_path / f"feature_security_report_{branch_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("Feature and security report saved to", output_path)
        warn_if_context_exceeded("feature and security report", combined_prompt)
        if copy_to_clipboard(combined_prompt):
            console.print(
                "  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.",
                style="green",
            )
        else:
            console.print("  • Copy the report from the path above to share with your AI assistant.", style="yellow")

    if workflow is not Workflow.COMPARE:
        console.print("\n[green bold]Done ✅[/]")
        console.print("[grey]You can open the markdown file in your editor or share it with your AI assistant.[/]")
        console.print("\n[cyan]Thank you for using multi-codex.\n[/]", style="bold")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
