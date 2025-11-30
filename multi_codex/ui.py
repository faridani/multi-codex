from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import tiktoken
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from . import core

POLL_INTERVAL_SECONDS = 30
TOKEN_WARNING_THRESHOLD = 128_000

console = Console()


@dataclass
class BranchSpec:
    """Holds info about a tracked branch."""

    name: str
    branch_markdown_path: Optional[Path] = None


def print_banner() -> None:
    banner = r"""
░███     ░███            ░██    ░██    ░██                             ░██
░████   ░████            ░██    ░██                                    ░██
░██░██ ░██░██ ░██    ░██ ░██ ░████████ ░██ ░███████   ░███████   ░████████  ░███████  ░██    ░██
░██ ░████ ░██ ░██    ░██ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██  ░██  ░██
░██  ░██  ░██ ░██    ░██ ░██    ░██    ░██░██        ░██    ░██ ░██    ░██ ░█████████   ░█████
░██       ░██ ░██   ░███ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██   ░███ ░██         ░██  ░██
░██       ░██  ░█████░██ ░██     ░████ ░██ ░███████   ░███████   ░█████░██  ░███████  ░██    ░██




Multi-branch solution evaluator for GitHub repos.
"""
    console.print(Panel.fit(banner, style="cyan", title="multi-codex"))


def ensure_local_clone(repo_url: str, repo_path: Path) -> None:
    if (repo_path / ".git").is_dir():
        console.print(f"Using existing local clone at: [bold green]{repo_path}[/bold green]")
        with console.status("Fetching latest changes from origin..."):
            core.run_git(repo_path, ["fetch", "origin", "--prune"])
        return

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"\nCloning repository into: [bold cyan]{repo_path}[/bold cyan]")
    cmd = ["git", "clone", repo_url, str(repo_path)]

    try:
        with console.status("Running git clone...", spinner="dots"):
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
    except FileNotFoundError:
        console.print("Error: 'git' command not found. Please install Git and try again.", style="bold red")
        raise typer.Exit(1)
    except subprocess.CalledProcessError as e:
        console.print("\nGit clone failed.", style="bold red")
        if e.stderr:
            console.print(e.stderr)
        raise typer.Exit(1)


def choose_from_list(options: List[str], prompt: str) -> str:
    if not options:
        raise ValueError("No options provided for selection")

    options_table = "\n".join(f"  [green]{idx}[/green]. {option}" for idx, option in enumerate(options, 1))

    while True:
        console.print(f"{prompt}\n{options_table}")
        raw = Prompt.ask("Enter the number of your choice")
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

    options_table = "\n".join(f"  [green]{idx}[/green]. {branch}" for idx, branch in enumerate(branches, 1))

    while True:
        console.print(f"{prompt}\n{options_table}")
        choice = Prompt.ask("Select a branch by number or name (or press Enter to cancel)", default="")
        choice = choice.strip()
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
    core.run_git(repo_path, ["fetch", "origin", "--prune"])
    branches = sorted(core.get_remote_branch_names(repo_path))

    if not branches:
        console.print("No remote branches found on origin. Exiting.", style="red")
        raise typer.Exit(1)

    choice = select_branch(branches, f"Select the branch to {action_label}:")
    if choice is None:
        console.print("No branch selected. Exiting.")
        raise typer.Exit(1)

    return choice


def prompt_for_project_spec() -> tuple[Optional[str], str]:
    console.print("\nProvide the specification/design document for this project.")
    console.print("Option 1: enter a file path.")
    console.print("Option 2: press Enter and paste the spec content (finish with a line containing only 'EOF').\n")

    while True:
        raw = Prompt.ask("Path to spec document (or press Enter to paste it now)", default="").strip()
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
            console.print("No specification content provided. Please provide a path or paste content.\n", style="yellow")
            continue

        return None, content


def copy_to_clipboard(text: str) -> bool:
    platform = os.sys.platform

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
    console.print(f"{label}: [cyan]{path}[/cyan]")


def estimate_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def warn_if_large_prompt(prompt_text: str) -> None:
    tokens = estimate_tokens(prompt_text)
    if tokens > TOKEN_WARNING_THRESHOLD:
        console.print(
            f"⚠️ The generated prompt is approximately {tokens:,} tokens, which exceeds the typical context window of standard models (>{TOKEN_WARNING_THRESHOLD:,} tokens).",
            style="bold yellow",
        )
    else:
        console.print(f"Estimated token count: {tokens:,}.", style="grey62")


async def prompt_confirm_async(message: str, default: bool = False) -> bool:
    return await asyncio.to_thread(Confirm.ask, message, default=default)


async def monitor_branches(repo_path: Path, poll_interval: int = POLL_INTERVAL_SECONDS) -> Dict[str, BranchSpec]:
    selected: Dict[str, BranchSpec] = {}
    seen_branches: Set[str] = set()

    console.print("\n[bold cyan]Monitoring origin for fresh branches...[/bold cyan]")
    console.print("[grey62]When a branch ships, you'll decide whether to add it to the evaluation queue.[/grey62]")
    console.print(
        "[grey62]Start analysis at any time or keep watching for more contenders. Press Ctrl+C when you're ready to switch to analysis.\n[/grey62]"
    )

    try:
        while True:
            try:
                await asyncio.to_thread(core.run_git, repo_path, ["fetch", "origin", "--prune"])
            except Exception:
                await asyncio.sleep(poll_interval)
                continue

            remote_branches = await asyncio.to_thread(core.get_remote_branch_names, repo_path)
            new_branches = sorted(remote_branches - seen_branches)

            for branch in new_branches:
                console.print(f"[green]●[/green] [bold magenta]New branch detected:[/bold magenta] [grey62]{branch}[/grey62]")
                add_prompt = f"Add '{branch}' to the evaluation lineup?"
                if await prompt_confirm_async(add_prompt, default=True):
                    selected[branch] = BranchSpec(name=branch)
                    console.print(f"Branch '{branch}' added to the evaluation set.\n", style="green")

                    start_now = await prompt_confirm_async(
                        "Start analysis now? (Otherwise I'll keep monitoring for more branches.)", default=False
                    )
                    if start_now:
                        console.print("\n[bold cyan]Starting analysis with the current set of branches...[/bold cyan]\n")
                        return selected
                else:
                    console.print(f"Skipping branch '{branch}'.", style="yellow")
                    start_prompt = "Would you like to start analysis with the branches already queued?"
                    if not selected:
                        start_prompt = "Start analysis now even though no branches are queued yet? (You can always resume monitoring.)"

                    if await prompt_confirm_async(start_prompt, default=False):
                        console.print("\n[bold cyan]Launching analysis with the current lineup...[/bold cyan]\n")
                        return selected

            seen_branches = remote_branches

            if selected:
                tracked = ", ".join(sorted(selected.keys()))
                console.print(f"Currently tracking branches: [grey62]{tracked}[/grey62]")

            await asyncio.sleep(poll_interval)

    except KeyboardInterrupt:
        console.print("\n\nStopping branch monitor and moving on to analysis...\n")

    return selected


def build_intro() -> None:
    intro = textwrap.dedent(
        """
        Multi-codex is your branch evaluator for Codex-style multi-solution workflows.
        Ask Codex for up to four different solutions, push each as its own branch, and let multi-codex
        gather them into a single, AI-ready brief. It highlights what each branch does well and what
        the winning branch should borrow from the others—all without calling the OpenAI API or adding
        surprise costs.
        """
    ).strip()
    console.print(intro, style="grey62")

    console.print("\n[bold magenta]What I will do for you:[/bold magenta]")
    steps = [
        "Monitor your GitHub repository for new branches in real time.",
        "Guide you through selecting the branches and attaching your spec or design doc.",
        "Generate rich markdown snapshots for every branch you pick.",
        "Assemble polished prompts you can paste straight into your AI UI for analysis and comparison.",
    ]
    for idx, step in enumerate(steps, 1):
        console.print(f"  [bold green]{idx})[/bold green] [grey62]{step}[/grey62]")
    console.print()


def handle_architecture(repo_path: Path, report_path: Path, branch_name: str) -> None:
    console.print(f"\nPreparing architectural report prompt for branch: [cyan]{branch_name}[/cyan]\n")
    combined_prompt = core.build_architecture_report(repo_path, branch_name)

    branch_slug = core.slugify_branch_name(branch_name)
    output_path = report_path / f"architecture_report_{branch_slug}.md"
    output_path.write_text(combined_prompt, encoding="utf-8")

    print_saved_file("Architectural report prompt saved to", output_path)
    warn_if_large_prompt(combined_prompt)
    if copy_to_clipboard(combined_prompt):
        console.print(
            "  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.",
            style="green",
        )
    else:
        console.print("  • Copy the report from the path above to share with your AI assistant.", style="yellow")


def handle_branch_comparison(repo_path: Path, report_path: Path, poll_interval: int) -> None:
    spec_path, spec_content = prompt_for_project_spec()

    branch_specs = asyncio.run(monitor_branches(repo_path, poll_interval=poll_interval))

    if not branch_specs:
        console.print("No branches were selected for evaluation. Exiting.")
        return

    console.print("Generating markdown snapshot for each selected branch...\n")
    branch_markdown: Dict[str, str] = {}

    for branch_name, bs in branch_specs.items():
        console.print(f"Processing branch: [cyan]{branch_name}[/cyan]")
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

    console.print("\n[bold magenta]Combined markdown saved to:[/bold magenta]")
    print_saved_file("  -> Path", combined_prompt_path)
    console.print("  (Contents intentionally not printed to avoid console noise)\n")

    warn_if_large_prompt(combined_prompt)
    copied = copy_to_clipboard(combined_prompt)
    console.print("[bold magenta]Next step: share with ChatGPT.[/bold magenta]")
    if copied:
        console.print("  • Combined prompt copied to your clipboard.", style="green")
    else:
        console.print("  • Copy the combined prompt file to your clipboard from the path above.", style="yellow")
    console.print("  • Open https://chatgpt.com/ and paste the contents into the UI to run the branch analysis.", style="grey62")

    console.print("\n[bold green]Done ✅[/bold green]")
    console.print("[grey62]You can open the markdown files in your editor to inspect:[/grey62]")
    print_saved_file("  - Combined specs + branches prompt", combined_prompt_path)
    console.print("\n[bold cyan]Thank you for using multi-codex.\n[/bold cyan]")


def handle_pr_review(repo_path: Path, report_path: Path, branch_name: str, base_branch: str) -> None:
    console.print(f"\nBuilding long-context snapshot for PR branch: [cyan]{branch_name}[/cyan]\n")
    combined_prompt = core.build_pr_mega_prompt(repo_path, branch_name, base_branch)

    branch_slug = core.slugify_branch_name(branch_name)
    base_slug = core.slugify_branch_name(base_branch)
    output_path = report_path / f"pr_review_prompt_{branch_slug}_vs_{base_slug}.md"
    output_path.write_text(combined_prompt, encoding="utf-8")

    print_saved_file("PR review mega prompt saved to", output_path)
    warn_if_large_prompt(combined_prompt)
    if copy_to_clipboard(combined_prompt):
        console.print("  • PR mega prompt copied to your clipboard.", style="green")
    else:
        console.print(
            "  • Copy the PR mega prompt from the path above to share with your AI assistant.",
            style="yellow",
        )


def handle_feature_security(repo_path: Path, report_path: Path, branch_name: str) -> None:
    console.print(f"\nPreparing feature and security analysis for branch: [cyan]{branch_name}[/cyan]\n")
    combined_prompt = core.build_feature_security_report(repo_path, branch_name)

    branch_slug = core.slugify_branch_name(branch_name)
    output_path = report_path / f"feature_security_report_{branch_slug}.md"
    output_path.write_text(combined_prompt, encoding="utf-8")

    print_saved_file("Feature and security report saved to", output_path)
    warn_if_large_prompt(combined_prompt)
    if copy_to_clipboard(combined_prompt):
        console.print(
            "  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.",
            style="green",
        )
    else:
        console.print("  • Copy the report from the path above to share with your AI assistant.", style="yellow")


app = typer.Typer(help="Multi-branch solution evaluator for GitHub repos.")


@app.command()
def run(
    repo_url: Optional[str] = typer.Option(None, "--repo", "-r", help="Git repository URL (HTTPS or SSH)."),
    workflow: Optional[str] = typer.Option(
        None,
        "--workflow",
        "-w",
        help="Workflow to run: architecture, compare, pr-review, feature-security.",
    ),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Branch name for single-branch workflows."),
    base_branch: str = typer.Option("main", "--base-branch", help="Base branch for PR review diffs."),
    poll_interval: int = typer.Option(POLL_INTERVAL_SECONDS, help="Polling interval (seconds) for branch monitoring."),
) -> None:
    print_banner()
    build_intro()

    repo_value = repo_url or Prompt.ask("Enter your GitHub repository URL (HTTPS or SSH)").strip()
    if not repo_value:
        console.print("Repository URL is required.", style="red")
        raise typer.Exit(1)

    repo_slug = core.slugify_repo_url(repo_value)
    repo_path, report_path = core.ensure_app_dirs(repo_slug)

    ensure_local_clone(repo_value, repo_path)

    options = [
        "architecture",
        "compare",
        "pr-review",
        "feature-security",
    ]

    if workflow and workflow not in options:
        console.print(f"Unknown workflow '{workflow}'. Choose from: {', '.join(options)}", style="red")
        raise typer.Exit(1)

    selected_option = workflow or choose_from_list(
        [
            "Analyze the architecture of a branch and produce an architectural report",
            "Compare branches and select the best one",
            "Prepare a PR review mega prompt with long context and a diff against the base branch",
            "Analyze a branch for features, security, and modernization opportunities",
        ],
        "Select the workflow you want to run:",
    )

    if selected_option in ("architecture", "Analyze the architecture of a branch and produce an architectural report"):
        branch_name = branch or prompt_for_branch_selection(repo_path, "analyze for architecture")
        handle_architecture(repo_path, report_path, branch_name)

    elif selected_option in ("compare", "Compare branches and select the best one"):
        console.print(f"Using polling interval: {poll_interval} seconds", style="grey62")
        handle_branch_comparison(repo_path, report_path, poll_interval)

    elif selected_option in (
        "pr-review",
        "Prepare a PR review mega prompt with long context and a diff against the base branch",
    ):
        branch_name = branch or prompt_for_branch_selection(repo_path, "convert to long context and diff for PR review")
        base_branch_input = Prompt.ask("Enter the base branch to diff against", default=base_branch).strip()
        handle_pr_review(repo_path, report_path, branch_name, base_branch_input or base_branch)

    else:
        branch_name = branch or prompt_for_branch_selection(repo_path, "analyze for features and security")
        handle_feature_security(repo_path, report_path, branch_name)

    if selected_option not in ("compare", "Compare branches and select the best one"):
        console.print("\n[bold green]Done ✅[/bold green]")
        console.print("[grey62]You can open the markdown file in your editor or share it with your AI assistant.[/grey62]")
        console.print("\n[bold cyan]Thank you for using multi-codex.\n[/bold cyan]")


if __name__ == "__main__":
    app()
