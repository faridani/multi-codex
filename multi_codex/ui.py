from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import core

POLL_INTERVAL_SECONDS = 30
TOKEN_WARNING_THRESHOLD = 128_000

console = Console()
app = typer.Typer(add_completion=False)

BANNER = r"""
░███     ░███            ░██    ░██    ░██                             ░██
░████   ░████            ░██    ░██                                    ░██
░██░██ ░██░██ ░██    ░██ ░██ ░████████ ░██ ░███████   ░███████   ░████████  ░███████  ░██    ░██
░██ ░████ ░██ ░██    ░██ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██  ░██  ░██
░██  ░██  ░██ ░██    ░██ ░██    ░██    ░██░██        ░██    ░██ ░██   ░███ ░██         ░█████
░██       ░██ ░██   ░███ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██   ░███ ░██         ░██  ░██
░██       ░██  ░█████░██ ░██     ░████ ░██ ░███████   ░███████   ░█████░██  ░███████  ░██    ░██




Multi-branch solution evaluator for GitHub repos.
"""


@dataclass
class BranchSpec:
    """Holds info about a tracked branch."""

    name: str
    branch_markdown_path: Optional[Path] = None


def print_banner() -> None:
    console.print(Panel(Markdown(BANNER), style="cyan"))


def input_non_empty(prompt: str) -> str:
    while True:
        value = typer.prompt(prompt).strip()
        if value:
            return value
        console.print("Please enter a non-empty value.\n", style="yellow")


def ensure_local_clone(repo_url: str, repo_path: Path) -> None:
    if (repo_path / ".git").is_dir():
        console.print(f"Using existing local clone at: [bold]{repo_path}[/bold]")
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Fetching origin...", start=True)
            core.run_git(repo_path, ["fetch", "origin", "--prune"])
            progress.update(task, description="Fetch complete")
        return

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"\nCloning repository into: [bold]{repo_path}[/bold]")

    cmd = ["git", "clone", repo_url, str(repo_path)]
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Cloning repository...", start=True)
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            progress.update(task, description="Clone complete")
        except FileNotFoundError:
            progress.stop()
            console.print(
                "Error: 'git' command not found. Please install Git and try again.",
                style="bold red",
            )
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            progress.stop()
            console.print("\nGit clone failed.", style="bold red")
            if e.stderr:
                console.print(e.stderr, style="red")
            sys.exit(1)


def choose_from_list(options: List[str], prompt: str) -> str:
    if not options:
        raise ValueError("No options provided for selection")

    table = Table(title=prompt)
    table.add_column("#", justify="right")
    table.add_column("Option")
    for idx, option in enumerate(options, 1):
        table.add_row(str(idx), option)

    console.print(table)

    while True:
        raw = typer.prompt("Enter the number of your choice").strip()
        if not raw.isdigit():
            console.print("Please enter a valid number.\n", style="yellow")
            continue

        idx = int(raw)
        if 1 <= idx <= len(options):
            return options[idx - 1]

        console.print("Choice out of range. Please try again.\n", style="yellow")


def select_branch(branches: List[str], prompt: str) -> Optional[str]:
    if not branches:
        raise ValueError("No branches available for selection")

    table = Table(title=prompt)
    table.add_column("#", justify="right")
    table.add_column("Branch")
    for idx, branch in enumerate(branches, 1):
        table.add_row(str(idx), branch)

    console.print(table)

    while True:
        choice = typer.prompt("Select a branch by number or name (or press Enter to cancel)", default="").strip()
        if not choice:
            return None

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(branches):
                return branches[idx - 1]
            console.print("Invalid branch number. Please choose a listed option.\n", style="yellow")
            continue

        if choice in branches:
            return choice

        console.print("Branch not recognized. Enter a listed number or an exact branch name.\n", style="yellow")


def prompt_for_branch_selection(repo_path: Path, action_label: str) -> str:
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Fetching branches...", start=True)
        core.run_git(repo_path, ["fetch", "origin", "--prune"])
        progress.update(task, description="Fetch complete")

    branches = sorted(core.get_remote_branch_names(repo_path))

    if not branches:
        console.print("No remote branches found on origin. Exiting.", style="red")
        sys.exit(1)

    choice = select_branch(branches, f"Select the branch to {action_label}:")
    if choice is None:
        console.print("No branch selected. Exiting.")
        sys.exit(1)

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
                console.print("That file does not exist. Please try again.\n", style="yellow")
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
                console.print(f"Error reading spec file: {e}\n", style="red")
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
            console.print(
                "No specification content provided. Please provide a path or paste content.\n",
                style="yellow",
            )
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
    console.print(f"{label}: [green]{path}[/green]")


def warn_token_count(label: str, text: str) -> None:
    count = core.count_tokens(text)
    status = f"Token estimate for {label}: [bold]{count}[/bold]"
    if count > TOKEN_WARNING_THRESHOLD:
        console.print(
            f"[yellow]{status} (exceeds {TOKEN_WARNING_THRESHOLD} tokens; may not fit standard context).[/yellow]"
        )
    else:
        console.print(status)


async def monitor_branches(repo_path: Path) -> Dict[str, BranchSpec]:
    selected: Dict[str, BranchSpec] = {}
    seen_branches: Set[str] = set()

    console.print("\nMonitoring origin for fresh branches...", style="cyan")
    console.print(
        "When a branch ships, you'll decide whether to add it to the evaluation queue.", style="bright_black"
    )
    console.print(
        "Start analysis at any time or keep watching for more contenders. Press Ctrl+C when you're ready to switch to analysis.\n",
        style="bright_black",
    )

    try:
        while True:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
                task = progress.add_task("Fetching origin...", start=True)
                try:
                    await asyncio.to_thread(core.run_git, repo_path, ["fetch", "origin", "--prune"])
                finally:
                    progress.update(task, description="Fetch complete")

            remote_branches = await asyncio.to_thread(core.get_remote_branch_names, repo_path)
            new_branches = sorted(remote_branches - seen_branches)

            for branch in new_branches:
                console.print(f"[green]●[/green] [magenta][bold]New branch detected:[/bold][/magenta] {branch}")
                add_prompt = (
                    f"[green]●[/green] [magenta][bold]Add[/bold][/magenta] '{branch}' to the evaluation lineup?"
                )
                if typer.confirm(add_prompt, default=True):
                    selected[branch] = BranchSpec(name=branch)
                    console.print(f"Branch '{branch}' added to the evaluation set.\n", style="green")

                    start_now = typer.confirm(
                        "Start analysis now? (Otherwise I'll keep monitoring for more branches.)",
                        default=False,
                    )
                    if start_now:
                        console.print(
                            "\nStarting analysis with the current set of branches...\n",
                            style="cyan",
                        )
                        return selected
                else:
                    console.print(f"Skipping branch '{branch}'.", style="yellow")
                    start_prompt = "Would you like to start analysis with the branches already queued?"
                    if not selected:
                        start_prompt = (
                            "Start analysis now even though no branches are queued yet? (You can always resume monitoring.)"
                        )

                    if typer.confirm(start_prompt, default=False):
                        console.print(
                            "\nLaunching analysis with the current lineup...\n",
                            style="cyan",
                        )
                        return selected

            seen_branches = remote_branches

            if selected:
                tracked = ", ".join(sorted(selected.keys()))
                console.print(f"Currently tracking branches: {tracked}", style="bright_black")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        console.print("\n\nStopping branch monitor and moving on to analysis...\n")

    return selected


@app.command()
def run() -> None:
    print_banner()

    intro = textwrap.dedent(
        """
        Multi-codex is your branch evaluator for Codex-style multi-solution workflows.
        Ask Codex for up to four different solutions, push each as its own branch, and let multi-codex
        gather them into a single, AI-ready brief. It highlights what each branch does well and what
        the winning branch should borrow from the others—all without calling the OpenAI API or adding
        surprise costs.
        """
    ).strip()
    console.print(Markdown(intro), style="bright_black")

    console.print("\nWhat I will do for you:", style="magenta")
    steps = [
        "Monitor your GitHub repository for new branches in real time.",
        "Guide you through selecting the branches and attaching your spec or design doc.",
        "Generate rich markdown snapshots for every branch you pick.",
        "Assemble polished prompts you can paste straight into your AI UI for analysis and comparison.",
    ]
    for idx, step in enumerate(steps, 1):
        console.print(f"  [green]{idx})[/green] {step}", style="bright_black")
    console.print()

    repo_url = input_non_empty("Enter your GitHub repository URL (HTTPS or SSH)")

    repo_slug = core.slugify_repo_url(repo_url)
    repo_path, report_path = core.ensure_app_dirs(repo_slug)

    ensure_local_clone(repo_url, repo_path)

    options = [
        "Analyze the architecture of a branch and produce an architectural report",
        "Compare branches and select the best one",
        "Prepare a PR review mega prompt with long context and a diff against the base branch",
        "Analyze a branch for features, security, and modernization opportunities",
    ]

    selected_option = choose_from_list(options, "Select the workflow you want to run:")

    if selected_option == options[0]:
        branch_name = prompt_for_branch_selection(repo_path, "analyze for architecture")
        console.print(f"\nPreparing architectural report prompt for branch: {branch_name}\n")
        combined_prompt = core.build_architecture_report(repo_path, branch_name)

        branch_slug = core.slugify_branch_name(branch_name)
        output_path = report_path / f"architecture_report_{branch_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("Architectural report prompt saved to", output_path)
        warn_token_count("architecture report", combined_prompt)
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

    elif selected_option == options[1]:
        spec_path, spec_content = prompt_for_project_spec()

        branch_specs = asyncio.run(monitor_branches(repo_path))

        if not branch_specs:
            console.print("No branches were selected for evaluation. Exiting.")
            return

        console.print("Generating markdown snapshot for each selected branch...\n")
        branch_markdown: Dict[str, str] = {}

        for branch_name, bs in branch_specs.items():
            console.print(f"Processing branch: {branch_name}")
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

        console.print("\nCombined markdown saved to:", style="magenta")
        print_saved_file("  -> Path", combined_prompt_path)
        console.print("  (Contents intentionally not printed to avoid console noise)\n", style="bright_black")

        warn_token_count("branch comparison", combined_prompt)

        copied = copy_to_clipboard(combined_prompt)
        console.print("Next step: share with ChatGPT.", style="magenta")
        if copied:
            console.print(
                "  • Combined prompt copied to your clipboard.",
                style="green",
            )
        else:
            console.print(
                "  • Copy the combined prompt file to your clipboard from the path above.",
                style="yellow",
            )
        console.print(
            "  • Open https://chatgpt.com/ and paste the contents into the UI to run the branch analysis.",
            style="bright_black",
        )

        console.print("\nDone ✅", style="green")
        console.print("You can open the markdown files in your editor to inspect:", style="bright_black")
        print_saved_file("  - Combined specs + branches prompt", combined_prompt_path)
        console.print("\nThank you for using multi-codex.\n", style="cyan")

    elif selected_option == options[2]:
        branch_name = prompt_for_branch_selection(repo_path, "convert to long context and diff for PR review")
        base_branch_input = typer.prompt("Enter the base branch to diff against", default="main").strip()
        base_branch = base_branch_input or "main"

        console.print(f"\nBuilding long-context snapshot for PR branch: {branch_name}\n")
        combined_prompt = core.build_pr_mega_prompt(repo_path, branch_name, base_branch)

        branch_slug = core.slugify_branch_name(branch_name)
        base_slug = core.slugify_branch_name(base_branch)
        output_path = report_path / f"pr_review_prompt_{branch_slug}_vs_{base_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("PR review mega prompt saved to", output_path)
        warn_token_count("PR review", combined_prompt)
        if copy_to_clipboard(combined_prompt):
            console.print(
                "  • PR mega prompt copied to your clipboard.",
                style="green",
            )
        else:
            console.print(
                "  • Copy the PR mega prompt from the path above to share with your AI assistant.",
                style="yellow",
            )

    else:
        branch_name = prompt_for_branch_selection(repo_path, "analyze for features and security")
        console.print(f"\nPreparing feature and security analysis for branch: {branch_name}\n")
        combined_prompt = core.build_feature_security_report(repo_path, branch_name)

        branch_slug = core.slugify_branch_name(branch_name)
        output_path = report_path / f"feature_security_report_{branch_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("Feature and security report saved to", output_path)
        warn_token_count("feature and security report", combined_prompt)
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

    if selected_option != options[1]:
        console.print("\nDone ✅", style="green")
        console.print("You can open the markdown file in your editor or share it with your AI assistant.", style="bright_black")
        console.print("\nThank you for using multi-codex.\n", style="cyan")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
