from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from . import core

POLL_INTERVAL_SECONDS = 30
COLOR = {
    "green": "\033[32m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "yellow": "\033[33m",
    "grey": "\033[90m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}
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


def color_text(text: str, *styles: str, bold: bool = False) -> str:
    """Wrap text in ANSI colors/styles."""

    codes: List[str] = []
    if bold:
        codes.append(COLOR["bold"])
    for style in styles:
        if style in COLOR:
            codes.append(COLOR[style])
    return "".join(codes) + text + COLOR["reset"]


def print_banner() -> None:
    print(color_text(BANNER, "cyan"))


def input_non_empty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Please enter a non-empty value.\n")


def ask_yes_no(prompt: str, default: bool = False, suffix: Optional[str] = None) -> bool:
    computed_suffix = suffix if suffix is not None else (" [Y/n]: " if default else " [y/N]: ")
    full_prompt = prompt.rstrip() + computed_suffix
    answer = input(full_prompt).strip().lower()

    if not answer:
        return default

    return answer in ("y", "yes")


def ensure_local_clone(repo_url: str, repo_path: Path) -> None:
    if (repo_path / ".git").is_dir():
        print(f"Using existing local clone at: {repo_path}")
        core.run_git(repo_path, ["fetch", "origin", "--prune"])
        return

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nCloning repository into: {repo_path}")
    cmd = ["git", "clone", repo_url, str(repo_path)]

    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        print("Error: 'git' command not found. Please install Git and try again.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print("\nGit clone failed.", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(1)


def choose_from_list(options: List[str], prompt: str) -> str:
    if not options:
        raise ValueError("No options provided for selection")

    while True:
        print(prompt)
        for idx, option in enumerate(options, 1):
            print(f"  {idx}. {option}")

        raw = input("Enter the number of your choice: ").strip()
        if not raw.isdigit():
            print("Please enter a valid number.\n")
            continue

        idx = int(raw)
        if 1 <= idx <= len(options):
            return options[idx - 1]

        print("Choice out of range. Please try again.\n")


def select_branch(branches: List[str], prompt: str) -> Optional[str]:
    if not branches:
        raise ValueError("No branches available for selection")

    while True:
        print(prompt)
        for idx, branch in enumerate(branches, 1):
            print(f"  {idx}. {branch}")

        choice = input("Select a branch by number or name (or press Enter to cancel): ").strip()
        if not choice:
            return None

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(branches):
                return branches[idx - 1]
            print("Invalid branch number. Please choose a listed option.\n")
            continue

        if choice in branches:
            return choice

        print("Branch not recognized. Enter a listed number or an exact branch name.\n")


def prompt_for_branch_selection(repo_path: Path, action_label: str) -> str:
    core.run_git(repo_path, ["fetch", "origin", "--prune"])
    branches = sorted(core.get_remote_branch_names(repo_path))

    if not branches:
        print("No remote branches found on origin. Exiting.")
        sys.exit(1)

    choice = select_branch(branches, f"Select the branch to {action_label}:")
    if choice is None:
        print("No branch selected. Exiting.")
        sys.exit(1)

    return choice


def prompt_for_project_spec() -> tuple[Optional[str], str]:
    print("\nProvide the specification/design document for this project.")
    print("Option 1: enter a file path.")
    print("Option 2: press Enter and paste the spec content (finish with a line containing only 'EOF').\n")

    while True:
        raw = input("Path to spec document (or press Enter to paste it now): ").strip()
        if raw:
            expanded = os.path.expanduser(raw)
            if not os.path.isfile(expanded):
                print("That file does not exist. Please try again.\n")
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
                print(f"Error reading spec file: {e}\n")
                continue

        print("\nPaste the specification content. End input with a single line containing only 'EOF'.")
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
            print("No specification content provided. Please provide a path or paste content.\n")
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
    print(f"{label}: {path}")


def monitor_branches(repo_path: Path) -> Dict[str, BranchSpec]:
    selected: Dict[str, BranchSpec] = {}
    seen_branches: Set[str] = set()

    print(color_text("\nMonitoring origin for fresh branches...", "cyan", bold=True))
    print(
        color_text(
            "When a branch ships, you'll decide whether to add it to the evaluation queue.",
            "grey",
        )
    )
    print(
        color_text(
            "Start analysis at any time or keep watching for more contenders. Press Ctrl+C when you're ready to switch to analysis.\n",
            "grey",
        )
    )

    try:
        while True:
            try:
                core.run_git(repo_path, ["fetch", "origin", "--prune"])
            except Exception:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            remote_branches = core.get_remote_branch_names(repo_path)
            new_branches = sorted(remote_branches - seen_branches)

            for branch in new_branches:
                print(
                    f"{color_text('●', 'green')} "
                    f"{color_text('New branch detected:', 'magenta', bold=True)} "
                    f"{color_text(branch, 'grey')}"
                )
                branch_label = f"'{branch}'"
                add_prompt = (
                    f"{color_text('●', 'green')} "
                    f"{color_text('Add', 'magenta', bold=True)} "
                    f"{color_text(branch_label, 'grey')} "
                    f"{color_text('to the evaluation lineup?', 'grey')}"
                )
                if ask_yes_no(add_prompt, default=True, suffix=f" {color_text('[Y/n]:', 'grey')} "):
                    selected[branch] = BranchSpec(name=branch)
                    print(
                        color_text(
                            f"Branch '{branch}' added to the evaluation set.\n",
                            "green",
                        )
                    )

                    if ask_yes_no(
                        color_text("Start analysis now?", "magenta", bold=True)
                        + " "
                        + color_text("(Otherwise I'll keep monitoring for more branches.)", "grey"),
                        default=False,
                        suffix=f" {color_text('[yes/ press enter for No]:', 'grey')} ",
                    ):
                        print(
                            color_text(
                                "\nStarting analysis with the current set of branches...\n",
                                "cyan",
                                bold=True,
                            )
                        )
                        return selected
                else:
                    print(color_text(f"Skipping branch '{branch}'.", "yellow"))
                    start_prompt = "Would you like to start analysis with the branches already queued?"
                    if not selected:
                        start_prompt = (
                            "Start analysis now even though no branches are queued yet? (You can always resume monitoring.)"
                        )

                    if ask_yes_no(
                        color_text(start_prompt, "magenta", bold=True),
                        default=False,
                        suffix=f" {color_text('[y/N]:', 'grey')} ",
                    ):
                        print(
                            color_text(
                                "\nLaunching analysis with the current lineup...\n",
                                "cyan",
                                bold=True,
                            )
                        )
                        return selected

            seen_branches = remote_branches

            if selected:
                tracked = ", ".join(sorted(selected.keys()))
                print(color_text(f"Currently tracking branches: {tracked}", "grey"))

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n\nStopping branch monitor and moving on to analysis...\n")

    return selected


def main() -> None:
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
    print(color_text(intro, "grey"))

    print(color_text("\nWhat I will do for you:", "magenta", bold=True))
    steps = [
        "Monitor your GitHub repository for new branches in real time.",
        "Guide you through selecting the branches and attaching your spec or design doc.",
        "Generate rich markdown snapshots for every branch you pick.",
        "Assemble polished prompts you can paste straight into your AI UI for analysis and comparison.",
    ]
    for idx, step in enumerate(steps, 1):
        print(f"  {color_text(str(idx) + ')', 'green', bold=True)} {color_text(step, 'grey')}")
    print()

    repo_url = input_non_empty("Enter your GitHub repository URL (HTTPS or SSH): ")

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
        print(f"\nPreparing architectural report prompt for branch: {branch_name}\n")
        combined_prompt = core.build_architecture_report(repo_path, branch_name)

        branch_slug = core.slugify_branch_name(branch_name)
        output_path = report_path / f"architecture_report_{branch_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("Architectural report prompt saved to", output_path)
        if copy_to_clipboard(combined_prompt):
            print(
                color_text(
                    "  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.",
                    "green",
                )
            )
        else:
            print(color_text("  • Copy the report from the path above to share with your AI assistant.", "yellow"))

    elif selected_option == options[1]:
        spec_path, spec_content = prompt_for_project_spec()

        branch_specs = monitor_branches(repo_path)

        if not branch_specs:
            print("No branches were selected for evaluation. Exiting.")
            return

        print("Generating markdown snapshot for each selected branch...\n")
        branch_markdown: Dict[str, str] = {}

        for branch_name, bs in branch_specs.items():
            print(f"Processing branch: {branch_name}")
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

        print(color_text("\nCombined markdown saved to:", "magenta", bold=True))
        print_saved_file("  -> Path", combined_prompt_path)
        print("  (Contents intentionally not printed to avoid console noise)\n")

        copied = copy_to_clipboard(combined_prompt)
        print(color_text("Next step: share with ChatGPT.", "magenta", bold=True))
        if copied:
            print(
                color_text(
                    "  • Combined prompt copied to your clipboard.",
                    "green",
                )
            )
        else:
            print(
                color_text(
                    "  • Copy the combined prompt file to your clipboard from the path above.",
                    "yellow",
                )
            )
        print(
            color_text(
                "  • Open https://chatgpt.com/ and paste the contents into the UI to run the branch analysis.",
                "grey",
            )
        )

        print(color_text("\nDone ✅", "green", bold=True))
        print(color_text("You can open the markdown files in your editor to inspect:", "grey"))
        print_saved_file("  - Combined specs + branches prompt", combined_prompt_path)
        print(color_text("\nThank you for using multi-codex.\n", "cyan", bold=True))

    elif selected_option == options[2]:
        branch_name = prompt_for_branch_selection(repo_path, "convert to long context and diff for PR review")
        base_branch_input = input("Enter the base branch to diff against [main]: ").strip()
        base_branch = base_branch_input or "main"

        print(f"\nBuilding long-context snapshot for PR branch: {branch_name}\n")
        combined_prompt = core.build_pr_mega_prompt(repo_path, branch_name, base_branch)

        branch_slug = core.slugify_branch_name(branch_name)
        base_slug = core.slugify_branch_name(base_branch)
        output_path = report_path / f"pr_review_prompt_{branch_slug}_vs_{base_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("PR review mega prompt saved to", output_path)
        if copy_to_clipboard(combined_prompt):
            print(
                color_text(
                    "  • PR mega prompt copied to your clipboard.",
                    "green",
                )
            )
        else:
            print(
                color_text(
                    "  • Copy the PR mega prompt from the path above to share with your AI assistant.",
                    "yellow",
                )
            )

    else:
        branch_name = prompt_for_branch_selection(repo_path, "analyze for features and security")
        print(f"\nPreparing feature and security analysis for branch: {branch_name}\n")
        combined_prompt = core.build_feature_security_report(repo_path, branch_name)

        branch_slug = core.slugify_branch_name(branch_name)
        output_path = report_path / f"feature_security_report_{branch_slug}.md"
        output_path.write_text(combined_prompt, encoding="utf-8")

        print_saved_file("Feature and security report saved to", output_path)
        if copy_to_clipboard(combined_prompt):
            print(
                color_text(
                    "  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.",
                    "green",
                )
            )
        else:
            print(color_text("  • Copy the report from the path above to share with your AI assistant.", "yellow"))

    if selected_option != options[1]:
        print(color_text("\nDone ✅", "green", bold=True))
        print(color_text("You can open the markdown file in your editor or share it with your AI assistant.", "grey"))
        print(color_text("\nThank you for using multi-codex.\n", "cyan", bold=True))


if __name__ == "__main__":
    main()
