from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

import questionary
import tiktoken
import typer
from questionary import Style as QStyle
from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from . import core

# Terminal and status icons (inspired by Claude Code)
ICON_TERMINAL = "❯"  # Terminal prompt indicator
ICON_THINKING = "◐"  # Thinking/processing indicator
ICON_SUCCESS = "✓"
ICON_WARNING = "⚠"
ICON_ERROR = "✗"
ICON_ARROW = "→"
ICON_BULLET = "•"
ICON_BRANCH = "⎇"
ICON_WORKFLOW = "⚡"

# Questionary custom style for arrow-key navigation
QUESTIONARY_STYLE = QStyle([
    ("qmark", "fg:#E91E63 bold"),
    ("question", "bold"),
    ("answer", "fg:#2196F3 bold"),
    ("pointer", "fg:#E91E63 bold"),
    ("highlighted", "fg:#E91E63 bold"),
    ("selected", "fg:#2196F3"),
    ("separator", "fg:#6C6C6C"),
    ("instruction", "fg:#808080"),
])

POLL_INTERVAL_SECONDS = 30
TOKEN_WARNING_THRESHOLD = 128_000

BANNER_LINES = [
    "░███     ░███            ░██    ░██    ░██                             ░██",
    "░████   ░████            ░██    ░██                                    ░██",
    "░██░██ ░██░██ ░██    ░██ ░██ ░████████ ░██ ░███████   ░███████   ░████████  ░███████  ░██    ░██",
    "░██ ░████ ░██ ░██    ░██ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██  ░██  ░██",
    "░██  ░██  ░██ ░██    ░██ ░██    ░██    ░██░██        ░██    ░██ ░██    ░██ ░█████████   ░█████",
    "░██       ░██ ░██   ░███ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██   ░███ ░██         ░██  ░██",
    "░██       ░██  ░█████░██ ░██     ░████ ░██ ░███████   ░███████   ░█████░██  ░███████  ░██    ░██",
    "",
    "",
    "",
    "Multi-branch solution evaluator for GitHub repos.",
]

LOGO_LINE_COUNT = 7
BANNER_COLORS = [
    "#4796E4",
    "#5A8EDB",
    "#6E86D3",
    "#847ACE",
    "#9B73B8",
    "#B46FA1",
    "#C3677F",
]


custom_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "danger": "bold red",
        "success": "green",
        "muted": "grey53",
    }
)

console = Console(theme=custom_theme)


@dataclass
class MenuAction:
    """Represents a menu item in the interactive flow."""

    key: str
    title: str
    description: str
    handler: Callable[[Path, Path], None]


@dataclass
class BranchSpec:
    """Holds info about a tracked branch."""

    name: str
    branch_markdown_path: Optional[Path] = None


def print_banner() -> None:
    banner_text = Text()
    for idx, line in enumerate(BANNER_LINES):
        if idx < LOGO_LINE_COUNT:
            style = BANNER_COLORS[idx % len(BANNER_COLORS)]
        else:
            style = "bright_white"
        banner_text.append(line, style=style)
        if idx < len(BANNER_LINES) - 1:
            banner_text.append("\n")

    styled_banner = Align.center(banner_text, vertical="middle")
    console.print(
        Panel(
            styled_banner,
            border_style="bright_magenta",
            padding=(1, 2),
            subtitle="multi-codex",
            subtitle_align="right",
        )
    )


def print_section(title: str, subtitle: str | None = None) -> None:
    rule_title = f"[bold cyan]{title}[/bold cyan]"
    if subtitle:
        rule_title += f" [grey53]{subtitle}[/grey53]"
    console.rule(rule_title)


def show_thinking(message: str = "Thinking") -> Live:
    """Create a live display showing a thinking/processing indicator."""
    spinner = Spinner("dots", text=f"[cyan]{message}...[/cyan]", style="cyan")
    return Live(spinner, console=console, refresh_per_second=10, transient=True)


def print_status(message: str, status: str = "info") -> None:
    """Print a status message with appropriate icon."""
    icons = {
        "success": (ICON_SUCCESS, "green"),
        "warning": (ICON_WARNING, "yellow"),
        "error": (ICON_ERROR, "red"),
        "info": (ICON_BULLET, "cyan"),
        "thinking": (ICON_THINKING, "magenta"),
    }
    icon, color = icons.get(status, (ICON_BULLET, "white"))
    console.print(f"[{color}]{icon}[/{color}] {message}")


def display_intro() -> None:
    intro = textwrap.dedent(
        """
        **Multi-codex** is your intelligent code analysis companion for GitHub repositories.

        Whether you're evaluating multiple solution branches from Codex-style workflows,
        reviewing pull requests, analyzing architecture, or hunting for security vulnerabilities—
        multi-codex helps you understand your codebase deeply and leverage AI coders effectively.

        **Key capabilities:**
        - 🔀 Compare many branches and identify the best approach
        - 🔍 Understand your codebase structure and architecture
        - 🛡️ Find security vulnerabilities and modernization opportunities
        - 📋 Prepare comprehensive PR reviews with full context
        - 🤖 Generate AI-ready prompts for Claude, ChatGPT, Gemini, Grok, DeepSeek, and other models

        All analysis runs locally—no API calls, no surprise costs.
        """
    ).strip()
    console.print(
        Panel(
            Markdown(intro),
            box=box.ROUNDED,
            border_style="cyan",
            padding=(1, 2),
            title=f"[bold cyan]{ICON_TERMINAL} Welcome[/bold cyan]",
            title_align="left",
        )
    )

    steps = [
        (f"{ICON_BRANCH} Monitor", "Watch your GitHub repository for new branches in real time"),
        (f"{ICON_ARROW} Guide", "Walk you through selecting branches and attaching specs or design docs"),
        (f"{ICON_BULLET} Snapshot", "Generate rich markdown snapshots of your entire codebase"),
        (f"{ICON_WORKFLOW} Analyze", "Run architecture, security, and feature analysis on any branch"),
        (f"{ICON_SUCCESS} Deliver", "Assemble polished prompts ready for your favorite AI coding assistant"),
    ]

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
        title=f"{ICON_WORKFLOW} How multi-codex helps",
        title_style="bold bright_white",
    )
    table.add_column("Action", style="cyan", width=14)
    table.add_column("What I will do for you", style="white")
    for action, description in steps:
        table.add_row(f"[bold]{action}[/bold]", description)

    console.print(Panel.fit(table, border_style="bright_black", padding=1))


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

    console.print(
        Panel(
            f"{ICON_BRANCH} {prompt}\n\n"
            f"Use [bold]↑/↓ arrow keys[/bold] to navigate, [bold]Enter[/bold] to select.",
            style="cyan",
            box=box.ROUNDED,
            title=f"[bold cyan]{ICON_BRANCH} Branch Selection[/bold cyan]",
            title_align="left",
        )
    )

    # Build choices for questionary
    choices = [questionary.Choice(title=f"{ICON_BRANCH} {branch}", value=branch) for branch in branches]
    choices.append(questionary.Choice(title=f"[Cancel] {ICON_ARROW} Go back", value=None))

    selected = questionary.select(
        f"{ICON_TERMINAL} Select a branch:",
        choices=choices,
        style=QUESTIONARY_STYLE,
        qmark=ICON_BRANCH,
        pointer=f"{ICON_TERMINAL}",
        instruction="(Use arrow keys, Enter to select)",
    ).ask()

    return selected


def prompt_for_branch_selection(repo_path: Path, action_label: str) -> str:
    with show_thinking("Fetching branches"):
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
            box=box.ROUNDED,
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


def run_architecture(repo_path: Path, report_path: Path) -> None:
    print_section("Architecture report", "Select a branch and assemble the prompt")
    branch_name = prompt_for_branch_selection(repo_path, "analyze for architecture")

    print_status(f"Analyzing architecture for branch: {branch_name}", "thinking")
    with show_thinking("Generating architecture report"):
        combined_prompt = core.build_architecture_report(repo_path, branch_name)

    branch_slug = core.slugify_branch_name(branch_name)
    output_path = report_path / f"architecture_report_{branch_slug}.md"
    save_and_notify(combined_prompt, output_path, "Architectural report prompt")

    print_status("Done! Open the markdown file in your editor or share with your AI assistant.", "success")


def run_compare(repo_path: Path, report_path: Path) -> None:
    print_section("Branch comparison", "Queue branches and merge specs")
    spec_path, spec_content = prompt_for_project_spec()

    branch_specs = asyncio.run(monitor_branches(repo_path))

    if not branch_specs:
        print_status("No branches were selected for evaluation. Exiting.", "warning")
        return

    print_status("Generating markdown snapshot for each selected branch...", "thinking")
    branch_markdown: Dict[str, str] = {}

    for branch_name, bs in branch_specs.items():
        with show_thinking(f"Processing branch: {branch_name}"):
            md_text = core.collect_branch_markdown(repo_path, branch_name)
        branch_markdown[branch_name] = md_text

        branch_slug = core.slugify_branch_name(branch_name)
        branch_md_path = report_path / f"branch_{branch_slug}.md"
        branch_md_path.write_text(md_text, encoding="utf-8")
        bs.branch_markdown_path = branch_md_path
        print_status(f"Branch markdown saved: {branch_md_path}", "success")

    with show_thinking("Building comparison prompt"):
        combined_prompt = core.build_branch_comparison_prompt(spec_path, spec_content, branch_markdown)
    combined_prompt_path = report_path / "combined_spec_and_branches.md"

    combined_prompt_path.write_text(combined_prompt, encoding="utf-8")

    console.print(
        Panel(
            f"{ICON_SUCCESS} Combined markdown saved.",
            style="magenta",
            title="Completed",
        )
    )
    print_saved_file(f"  {ICON_ARROW} Path", combined_prompt_path)
    console.print("  (Contents intentionally not printed to avoid console noise)\n")

    copied = copy_to_clipboard(combined_prompt)
    print_status("Next step: share with your AI assistant (Claude, ChatGPT, Gemini, etc.)", "info")
    if copied:
        print_status("Combined prompt copied to your clipboard.", "success")
    else:
        print_status("Copy the combined prompt file to your clipboard from the path above.", "warning")

    warn_if_large("Combined spec and branches prompt", combined_prompt)
    print_status("Done! Thank you for using multi-codex.", "success")


def run_pr_review(repo_path: Path, report_path: Path) -> None:
    print_section("PR review", "Capture long-context snapshots and diffs")
    branch_name = prompt_for_branch_selection(
        repo_path, "convert to long context and diff for PR review"
    )
    base_branch = typer.prompt(f"{ICON_TERMINAL} Base branch to diff against", default="main").strip()

    print_status(f"Building long-context snapshot for PR: {branch_name} vs {base_branch}", "thinking")
    with show_thinking("Generating PR review mega prompt"):
        combined_prompt = core.build_pr_mega_prompt(repo_path, branch_name, base_branch)

    branch_slug = core.slugify_branch_name(branch_name)
    base_slug = core.slugify_branch_name(base_branch)
    output_path = report_path / f"pr_review_prompt_{branch_slug}_vs_{base_slug}.md"
    save_and_notify(combined_prompt, output_path, "PR review mega prompt")


def run_feature_security(repo_path: Path, report_path: Path) -> None:
    print_section("Feature & security", "Select a branch to evaluate")
    branch_name = prompt_for_branch_selection(repo_path, "analyze for features and security")

    print_status(f"Analyzing features and security for branch: {branch_name}", "thinking")
    with show_thinking("Generating feature and security report"):
        combined_prompt = core.build_feature_security_report(repo_path, branch_name)

    branch_slug = core.slugify_branch_name(branch_name)
    output_path = report_path / f"feature_security_report_{branch_slug}.md"
    save_and_notify(combined_prompt, output_path, "Feature and security report")

    print_status("Done! Open the markdown file in your editor or share with your AI assistant.", "success")


def choose_action(actions: List[MenuAction]) -> Optional[MenuAction]:
    console.print(
        Panel(
            f"{ICON_TERMINAL} Select a workflow using [bold]↑/↓ arrow keys[/bold] and press [bold]Enter[/bold] to confirm.",
            style="cyan",
            box=box.ROUNDED,
            title=f"[bold cyan]{ICON_WORKFLOW} Available Workflows[/bold cyan]",
            title_align="left",
        )
    )

    # Build choices for questionary with descriptions
    choices = []
    for action in actions:
        # Format: "Title - Description"
        label = f"{action.title} {ICON_ARROW} {action.description}"
        choices.append(questionary.Choice(title=label, value=action.key))

    choices.append(questionary.Choice(title=f"[Exit] {ICON_ARROW} Cancel and exit multi-codex", value="exit"))

    selected = questionary.select(
        f"{ICON_TERMINAL} Choose a workflow:",
        choices=choices,
        style=QUESTIONARY_STYLE,
        qmark=ICON_WORKFLOW,
        pointer=f"{ICON_TERMINAL}",
        instruction="(Use arrow keys to navigate, Enter to select)",
    ).ask()

    if selected is None or selected == "exit":
        return None

    # Find and return the matching action
    for action in actions:
        if action.key == selected:
            return action

    return None


def launch_interactive() -> None:
    print_banner()
    display_intro()

    console.print(
        Panel(
            f"{ICON_TERMINAL} Let's get your repository ready. "
            "I'll clone it locally if needed, then you can pick what to do next.",
            style="magenta",
            box=box.ROUNDED,
            title=f"[bold magenta]{ICON_WORKFLOW} Getting Started[/bold magenta]",
            title_align="left",
        )
    )

    _, repo_path, report_path = prepare_repository(None)
    print_status("Repository ready!", "success")

    actions = [
        MenuAction(
            key="architecture",
            title="🏗️  Architecture",
            description="Analyze the architecture of a branch and produce an architectural report.",
            handler=run_architecture,
        ),
        MenuAction(
            key="compare",
            title="🔀 Compare",
            description="Compare branches and select the best one.",
            handler=run_compare,
        ),
        MenuAction(
            key="pr-review",
            title="📋 PR Review",
            description="Prepare a PR review mega prompt with long context and a diff.",
            handler=run_pr_review,
        ),
        MenuAction(
            key="feature-security",
            title="🛡️  Security",
            description="Analyze a branch for features, security, and modernization.",
            handler=run_feature_security,
        ),
    ]

    action = choose_action(actions)

    if action is None:
        print_status("No action selected. Goodbye!", "info")
        raise typer.Exit(code=0)

    print_status(f"Starting: {action.title}", "info")
    console.print()
    action.handler(repo_path, report_path)


def main() -> None:
    launch_interactive()


if __name__ == "__main__":
    main()
