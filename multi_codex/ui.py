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

import tiktoken
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from . import core

POLL_INTERVAL_SECONDS = 30
TOKEN_WARNING_THRESHOLD = 128_000

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


console = Console()
app = typer.Typer(add_completion=False, help="Generate AI-ready reports for Git branches.")


@dataclass
class BranchSpec:
    """Holds info about a tracked branch."""

    name: str
    branch_markdown_path: Optional[Path] = None


def print_banner() -> None:
    console.print(Panel.fit(Markdown(f"```\n{BANNER}\n```"), border_style="cyan"))


def display_intro() -> None:
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

    steps = [
        "Monitor your GitHub repository for new branches in real time.",
        "Guide you through selecting the branches and attaching your spec or design doc.",
        "Generate rich markdown snapshots for every branch you pick.",
        "Assemble polished prompts you can paste straight into your AI UI for analysis and comparison.",
    ]

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Step #", style="cyan", width=8)
    table.add_column("What I will do for you")
    for idx, step in enumerate(steps, 1):
        table.add_row(str(idx), step)

    console.print(table)


def prompt_repo_url(repo_url: Optional[str]) -> str:
    while True:
        url = repo_url or typer.prompt("Enter your GitHub repository URL (HTTPS or SSH)").strip()
        if url:
            return url
        console.print("[yellow]Please provide a repository URL.[/yellow]")
        repo_url = None


def ensure_local_clone(repo_url: str, repo_path: Path) -> None:
    if (repo_path / ".git").is_dir():
        console.print(f"[green]Using existing local clone at {repo_path}[/green]")
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            TimeElapsedColumn(),
            transient=True,
            console=console,
        ) as progress:
            fetch_task = progress.add_task("Fetching latest changes from origin...", start=True)
            core.run_git(repo_path, ["fetch", "origin", "--prune"])
            progress.update(fetch_task, advance=1)
        return

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    console.print(Panel.fit(f"Cloning repository into {repo_path}", style="cyan"))
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        clone_task = progress.add_task("Cloning repository...", start=False, total=None)
        progress.start_task(clone_task)
        try:
            subprocess.run(
                ["git", "clone", repo_url, str(repo_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            progress.update(clone_task, advance=1)
        except FileNotFoundError:
            console.print("[red]Error: 'git' command not found. Please install Git and try again.[/red]")
            raise typer.Exit(code=1)
        except subprocess.CalledProcessError as e:
            console.print("[red]Git clone failed.[/red]")
            if e.stderr:
                console.print(Panel(e.stderr, title="Git error", style="red"))
            raise typer.Exit(code=1)


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


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    return typer.confirm(prompt, default=default)


def select_branch(branches: List[str], prompt: str) -> Optional[str]:
    if not branches:
        raise ValueError("No branches available for selection")

    while True:
        console.print(Panel(prompt, style="cyan"))
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", width=4, style="cyan")
        table.add_column("Branch", style="green")
        for idx, branch in enumerate(branches, 1):
            table.add_row(str(idx), branch)
        console.print(table)

        choice = typer.prompt("Select a branch by number or name (or press Enter to cancel)", default="")
        choice = choice.strip()
        if not choice:
            return None

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(branches):
                return branches[idx - 1]
            console.print("[yellow]Invalid branch number. Please choose a listed option.[/yellow]\n")
            continue

        if choice in branches:
            return choice

        console.print("[yellow]Branch not recognized. Enter a listed number or an exact branch name.[/yellow]\n")


def prompt_for_branch_selection(repo_path: Path, action_label: str) -> str:
    core.run_git(repo_path, ["fetch", "origin", "--prune"])
    branches = sorted(core.get_remote_branch_names(repo_path))

    if not branches:
        console.print("[red]No remote branches found on origin. Exiting.[/red]")
        raise typer.Exit(code=1)

    choice = select_branch(branches, f"Select the branch to {action_label}:")
    if choice is None:
        console.print("[yellow]No branch selected. Exiting.[/yellow]")
        raise typer.Exit(code=1)

    return choice


def prompt_for_project_spec() -> tuple[Optional[str], str]:
    console.print(
        Panel(
            "Provide the specification/design document for this project.\n"
            "Option 1: enter a file path.\n"
            "Option 2: press Enter and paste the spec content (finish with a line containing only 'EOF').",
            style="magenta",
        )
    )

    while True:
        raw = typer.prompt("Path to spec document (or press Enter to paste it now)", default="").strip()
        if raw:
            expanded = os.path.expanduser(raw)
            if not os.path.isfile(expanded):
                console.print("[yellow]That file does not exist. Please try again.[/yellow]\n")
                continue

            try:
                with open(expanded, "r", encoding="utf-8") as f:
                    content = f.read()
                return expanded, content
            except UnicodeDecodeError:
                with open(expanded, "r", encoding="latin-1") as f:
                    content = f.read()
                return expanded, content
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Error reading spec file: {exc}[/red]\n")
                continue

        console.print("Paste the specification content. End input with a single line containing only 'EOF'.")
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
            console.print("[yellow]No specification content provided. Please provide a path or paste content.[/yellow]\n")
            continue

        return None, content


def print_saved_file(label: str, path: Path) -> None:
    console.print(f"{label}: [cyan]{path}[/cyan]")


async def monitor_branches(repo_path: Path) -> Dict[str, BranchSpec]:
    selected: Dict[str, BranchSpec] = {}
    seen_branches: Set[str] = set()

    console.print(
        Panel(
            "Monitoring origin for fresh branches. When a branch ships, you'll decide whether to add it to the evaluation queue.\n"
            "Start analysis at any time or keep watching for more contenders. Press Ctrl+C when you're ready to switch to analysis.",
            style="cyan",
        )
    )

    try:
        while True:
            try:
                await asyncio.to_thread(core.run_git, repo_path, ["fetch", "origin", "--prune"])
            except Exception:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            remote_branches = core.get_remote_branch_names(repo_path)
            new_branches = sorted(remote_branches - seen_branches)

            for branch in new_branches:
                console.print(f"[green]● New branch detected:[/green] [grey]{branch}[/grey]")
                branch_label = f"'{branch}'"
                add_prompt = f"Add {branch_label} to the evaluation lineup?"
                if ask_yes_no(add_prompt, default=True):
                    selected[branch] = BranchSpec(name=branch)
                    console.print(f"[green]Branch '{branch}' added to the evaluation set.[/green]\n")

                    if ask_yes_no("Start analysis now? (Otherwise I'll keep monitoring for more branches.)", default=False):
                        console.print("[cyan]Starting analysis with the current set of branches...[/cyan]\n")
                        return selected
                else:
                    console.print(f"[yellow]Skipping branch '{branch}'.[/yellow]")
                    start_prompt = "Would you like to start analysis with the branches already queued?"
                    if not selected:
                        start_prompt = "Start analysis now even though no branches are queued yet? (You can always resume monitoring.)"

                    if ask_yes_no(start_prompt, default=False):
                        console.print("[cyan]Launching analysis with the current lineup...[/cyan]\n")
                        return selected

            seen_branches = remote_branches

            if selected:
                tracked = ", ".join(sorted(selected.keys()))
                console.print(f"[grey]Currently tracking branches: {tracked}[/grey]")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        console.print("\n[cyan]Stopping branch monitor and moving on to analysis...[/cyan]\n")

    return selected


def compute_token_count(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def warn_if_large(label: str, text: str) -> None:
    tokens = compute_token_count(text)
    if tokens > TOKEN_WARNING_THRESHOLD:
        console.print(
            Panel(
                f"{label} is approximately {tokens} tokens, which exceeds the typical 128k-token context window."
                " Consider trimming the document or using a larger-context model.",
                title="Token warning",
                style="red",
            )
        )
    else:
        console.print(f"[green]{label} token estimate: {tokens} tokens.[/green]")


def save_and_notify(prompt_text: str, output_path: Path, label: str) -> None:
    output_path.write_text(prompt_text, encoding="utf-8")
    print_saved_file(label, output_path)
    warn_if_large(label, prompt_text)
    if copy_to_clipboard(prompt_text):
        console.print("[green]• Content copied to your clipboard.[/green]")
    else:
        console.print("[yellow]• Copy the prompt from the saved file to share with your AI assistant.[/yellow]")


def prepare_repository(repo_url: Optional[str]) -> tuple[str, Path, Path]:
    repo_url_value = prompt_repo_url(repo_url)
    repo_slug = core.slugify_repo_url(repo_url_value)
    repo_path, report_path = core.ensure_app_dirs(repo_slug)
    ensure_local_clone(repo_url_value, repo_path)
    return repo_url_value, repo_path, report_path


@app.command()
def architecture(
    repo_url: Optional[str] = typer.Option(None, help="Repository URL to analyze."),
    branch: Optional[str] = typer.Option(None, help="Branch to analyze for architecture."),
) -> None:
    """Analyze the architecture of a branch and produce an architectural report."""

    print_banner()
    display_intro()

    _, repo_path, report_path = prepare_repository(repo_url)
    branch_name = branch or prompt_for_branch_selection(repo_path, "analyze for architecture")
    console.print(f"\n[cyan]Preparing architectural report prompt for branch: {branch_name}[/cyan]\n")
    combined_prompt = core.build_architecture_report(repo_path, branch_name)

    branch_slug = core.slugify_branch_name(branch_name)
    output_path = report_path / f"architecture_report_{branch_slug}.md"
    save_and_notify(combined_prompt, output_path, "Architectural report prompt")

    console.print("\n[cyan]Done ✅ You can open the markdown file in your editor or share it with your AI assistant.[/cyan]")


@app.command()
def compare(
    repo_url: Optional[str] = typer.Option(None, help="Repository URL to compare branches for."),
    spec: Optional[str] = typer.Option(None, help="Optional path to the project specification."),
) -> None:
    """Compare branches and select the best one."""

    print_banner()
    display_intro()

    _, repo_path, report_path = prepare_repository(repo_url)
    spec_path = None
    spec_content = ""
    if spec:
        try:
            with open(spec, "r", encoding="utf-8") as f:
                spec_content = f.read()
            spec_path = spec
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Failed to read spec at {spec}: {exc}[/red]")
            raise typer.Exit(code=1)
    else:
        spec_path, spec_content = prompt_for_project_spec()

    branch_specs = asyncio.run(monitor_branches(repo_path))

    if not branch_specs:
        console.print("[yellow]No branches were selected for evaluation. Exiting.[/yellow]")
        return

    console.print("[cyan]Generating markdown snapshot for each selected branch...[/cyan]\n")
    branch_markdown: Dict[str, str] = {}

    for branch_name, bs in branch_specs.items():
        console.print(f"Processing branch: [green]{branch_name}[/green]")
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

    console.print(Panel("Combined markdown saved.", style="magenta", title="Completed"))
    print_saved_file("  -> Path", combined_prompt_path)
    console.print("  (Contents intentionally not printed to avoid console noise)\n")

    copied = copy_to_clipboard(combined_prompt)
    console.print("[magenta]Next step: share with ChatGPT.[/magenta]")
    if copied:
        console.print("  • [green]Combined prompt copied to your clipboard.[/green]")
    else:
        console.print("  • [yellow]Copy the combined prompt file to your clipboard from the path above.[/yellow]")
    console.print(
        "  • [grey]Open https://chatgpt.com/ and paste the contents into the UI to run the branch analysis.[/grey]"
    )

    warn_if_large("Combined spec and branches prompt", combined_prompt)
    console.print("\n[cyan]Done ✅ Thank you for using multi-codex.[/cyan]\n")


@app.command("pr-review")
def pr_review(
    repo_url: Optional[str] = typer.Option(None, help="Repository URL to analyze."),
    branch: Optional[str] = typer.Option(None, help="PR branch to analyze."),
    base_branch: str = typer.Option("main", help="Base branch to diff against."),
) -> None:
    """Prepare a PR review mega prompt with long context and a diff against the base branch."""

    print_banner()
    display_intro()

    _, repo_path, report_path = prepare_repository(repo_url)
    branch_name = branch or prompt_for_branch_selection(
        repo_path, "convert to long context and diff for PR review"
    )
    console.print(f"\n[cyan]Building long-context snapshot for PR branch: {branch_name}[/cyan]\n")
    combined_prompt = core.build_pr_mega_prompt(repo_path, branch_name, base_branch)

    branch_slug = core.slugify_branch_name(branch_name)
    base_slug = core.slugify_branch_name(base_branch)
    output_path = report_path / f"pr_review_prompt_{branch_slug}_vs_{base_slug}.md"
    save_and_notify(combined_prompt, output_path, "PR review mega prompt")


@app.command("feature-security")
def feature_security(
    repo_url: Optional[str] = typer.Option(None, help="Repository URL to analyze."),
    branch: Optional[str] = typer.Option(None, help="Branch to analyze for features and security."),
) -> None:
    """Analyze a branch for features, security, and modernization opportunities."""

    print_banner()
    display_intro()

    _, repo_path, report_path = prepare_repository(repo_url)
    branch_name = branch or prompt_for_branch_selection(repo_path, "analyze for features and security")
    console.print(f"\n[cyan]Preparing feature and security analysis for branch: {branch_name}[/cyan]\n")
    combined_prompt = core.build_feature_security_report(repo_path, branch_name)

    branch_slug = core.slugify_branch_name(branch_name)
    output_path = report_path / f"feature_security_report_{branch_slug}.md"
    save_and_notify(combined_prompt, output_path, "Feature and security report")

    console.print("\n[cyan]Done ✅ You can open the markdown file in your editor or share it with your AI assistant.[/cyan]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
