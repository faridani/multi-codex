#!/usr/bin/env python3
"""
multi_codex.py

Multi-codex is a branch comparison companion for GitHub repositories. It helps
you evaluate multiple AI-generated solutions side by side by exporting each
branch into markdown and assembling a ready-to-paste prompt that highlights
coverage gaps and winning ideas.

Requirements:
- Python 3.9+
- git installed and configured (so that it can access your private repos)

Optional:
- Add an executable wrapper so you can run it as `multi-codex`.
"""

import os
import sys
import time
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# -----------------------
# Presentation constants
# -----------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[90m"
GREEN = "\033[92m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
YELLOW = "\033[93m"
WHITE = "\033[97m"

# -----------------------
# Configuration constants
# -----------------------

APP_DIR_NAME = ".multi_codex"

POLL_INTERVAL_SECONDS = 30  # how often to poll for new branches
MAX_FILE_SIZE_BYTES = 200 * 1024  # skip files larger than 200KB
IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
}

BANNER = rf"""
{CYAN}░███     ░███            ░██    ░██    ░██                             ░██{RESET}
{CYAN}░████   ░████            ░██    ░██                                    ░██{RESET}
{CYAN}░██░██ ░██░██ ░██    ░██ ░██ ░████████ ░██ ░███████   ░███████   ░████████  ░███████  ░██    ░██{RESET}
{CYAN}░██ ░████ ░██ ░██    ░██ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██  ░██  ░██{RESET}
{CYAN}░██  ░██  ░██ ░██    ░██ ░██    ░██    ░██░██        ░██    ░██ ░██    ░██ ░█████████   ░█████{RESET}
{CYAN}░██       ░██ ░██   ░███ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██   ░███ ░██         ░██  ░██{RESET}
{CYAN}░██       ░██  ░█████░██ ░██     ░████ ░██ ░███████   ░███████   ░█████░██  ░███████  ░██    ░██{RESET}

{MAGENTA}{BOLD}multi-codex • Branch comparison companion for AI-generated solutions{RESET}
"""

INSTRUCTION_PROMPT = (
    "You are an expert reviewer who specializes in translating specs into feature checklists, "
    "auditing code for coverage, and surfacing missed ideas.\n"
    "You will receive a combined markdown file that contains:\n"
    "1) The product specification or prompt.\n"
    "2) The contents of several Git branches (paths + file bodies).\n"
    "\n"
    "Please:\n"
    "- Derive a crisp list of features/requirements from the spec.\n"
    "- Build a MARKDOWN TABLE with features as rows and branch names as columns, "
    "marking each cell 'Yes' or 'No' based only on branch content.\n"
    "- Avoid speculation—cite only what the code demonstrates.\n"
    "- After the table, briefly explain how you chose the strongest branch, name it explicitly, "
    "and list the features it still lacks or only partially covers."
)


# -----------------------
# Data structures
# -----------------------

@dataclass
class BranchSpec:
    """Holds info about a tracked branch."""
    name: str
    branch_markdown_path: Optional[str] = None


# -----------------------
# Small utilities
# -----------------------

def print_banner() -> None:
    """Print a nice banner."""
    print(BANNER)
    print(f"{DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}\n")


def input_non_empty(prompt: str) -> str:
    """Prompt until user provides a non-empty response."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print(f"{YELLOW}Please enter a non-empty value.{RESET}\n")


def ask_yes_no(prompt: str, default: bool = False, suffix: Optional[str] = None) -> bool:
    """
    Ask a yes/no question.

    Returns True for yes, False for no.
    """
    computed_suffix = suffix if suffix is not None else (" [Y/n]: " if default else " [y/N]: ")
    full_prompt = prompt.rstrip() + computed_suffix
    answer = input(full_prompt).strip().lower()

    if not answer:
        return default

    return answer in ("y", "yes")


def slugify_repo_url(url: str) -> str:
    """
    Convert a GitHub repository URL into a filesystem-friendly slug.
    Examples:
        https://github.com/user/repo.git -> user_repo
        git@github.com:user/repo.git     -> user_repo
    """
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]

    # ssh form: git@github.com:user/repo
    if url.startswith("git@"):
        after_colon = url.split(":", 1)[1]
        path_part = after_colon.strip("/")
    else:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path_part = (parsed.path or "").lstrip("/")

    if not path_part:
        return "unknown_repo"

    slug = path_part.replace("/", "_").replace(".", "_").lower()
    return slug


def ensure_app_dirs(repo_slug: str) -> (str, str):
    """
    Create/return the app directories:
    - ~/.multi_codex/repos/<slug> (git clone)
    - ~/.multi_codex/reports/<slug> (markdown exports)
    """
    home = os.path.expanduser("~")
    app_root = os.path.join(home, APP_DIR_NAME)
    repos_root = os.path.join(app_root, "repos")
    reports_root = os.path.join(app_root, "reports")

    os.makedirs(repos_root, exist_ok=True)
    os.makedirs(reports_root, exist_ok=True)

    repo_path = os.path.join(repos_root, repo_slug)
    report_path = os.path.join(reports_root, repo_slug)
    os.makedirs(report_path, exist_ok=True)

    return repo_path, report_path


def run_git(repo_path: str, args: List[str]) -> str:
    """Run a git command in the given repo directory and return stdout."""
    cmd = ["git", "-C", repo_path] + args

    try:
        result = subprocess.run(
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
        print(f"\nGit error while running: {' '.join(cmd)}", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        raise

    return result.stdout.strip()


def ensure_local_clone(repo_url: str, repo_path: str) -> None:
    """
    Ensure we have a local clone of the repo at repo_path.
    Uses your existing git/GitHub authentication.
    """
    if os.path.isdir(os.path.join(repo_path, ".git")):
        print(f"Using existing local clone at: {repo_path}")
        # Update just in case
        run_git(repo_path, ["fetch", "origin", "--prune"])
        return

    os.makedirs(os.path.dirname(repo_path), exist_ok=True)
    print(f"\nCloning repository into: {repo_path}")
    cmd = ["git", "clone", repo_url, repo_path]

    try:
        result = subprocess.run(
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


def get_remote_branch_names(repo_path: str) -> Set[str]:
    """
    Return a set of remote branch names (without the 'origin/' prefix).
    Example: {'main', 'feature/login-ui'}
    """
    out = run_git(repo_path, ["branch", "-r", "--format", "%(refname:short)"])
    branches: Set[str] = set()

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("origin/"):
            continue
        name = line.split("/", 1)[1]  # drop "origin/"
        if name == "HEAD":
            continue
        branches.add(name)

    return branches


def prompt_for_project_spec() -> (Optional[str], str):
    """
    Ask once for the project-wide specification/design document.
    Returns (path_or_None, content). Requires either a path or pasted content.
    """
    print(f"\n{WHITE}Provide the specification or design document for this project.{RESET}")
    print(f"{DIM}Option 1:{RESET} enter a file path.")
    print(f"{DIM}Option 2:{RESET} press Enter and paste the spec content (finish with a line containing only 'EOF').\n")

    while True:
        raw = input("Path to spec document (or press Enter to paste it now): ").strip()
        if raw:
            expanded = os.path.expanduser(raw)
            if not os.path.isfile(expanded):
                print(f"{YELLOW}That file does not exist. Please try again.{RESET}\n")
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
                print(f"{YELLOW}Error reading spec file:{RESET} {e}\n")
                continue

        print(f"\n{CYAN}Paste the specification content. End input with a single line containing only 'EOF'.{RESET}")
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
            print(f"{YELLOW}No specification content provided. Please provide a path or paste content.{RESET}\n")
            continue

        return None, content


def is_binary_content(sample: bytes) -> bool:
    """Detect binary file by presence of NULL byte in a sample."""
    return b"\0" in sample


def read_text_file(path: str) -> Optional[str]:
    """
    Read a file as text, skipping binary and very large files.
    Returns None if it should be skipped.
    """
    try:
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE_BYTES:
            return None

        with open(path, "rb") as f:
            sample = f.read(4096)
            if is_binary_content(sample):
                return None

        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception:
            return None
    except Exception:
        return None


def slugify_branch_name(branch_name: str) -> str:
    """
    Convert a branch name into a filesystem-friendly slug.
    e.g. feature/login-ui -> feature_login_ui
    """
    return (
        branch_name.replace("/", "_")
        .replace(" ", "_")
        .replace("#", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def sync_remote_branch(repo_path: str, branch_name: str) -> None:
    """
    Make sure we have a local branch with the remote content.
    This will create/update a local branch that tracks origin/<branch_name>.
    """
    # Ensure origin is up-to-date
    run_git(repo_path, ["fetch", "origin", "--prune"])

    # Create/update local branch to match origin
    run_git(repo_path, ["checkout", "-q", "-B", branch_name, f"origin/{branch_name}"])


def collect_branch_markdown(repo_path: str, branch_name: str) -> str:
    """
    Check out a branch and turn all (reasonable) files into a big markdown document.
    """
    sync_remote_branch(repo_path, branch_name)

    lines: List[str] = []
    lines.append(f"# Branch `{branch_name}` contents\n")

    for root, dirs, files in os.walk(repo_path):
        # prune ignored dirs
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file_name in sorted(files):
            full_path = os.path.join(root, file_name)
            rel_path = os.path.relpath(full_path, repo_path)

            text = read_text_file(full_path)
            if text is None:
                continue

            lines.append(f"## `{rel_path}`")
            lines.append("")
            lines.append("```")
            lines.append(text.rstrip())
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def print_saved_file(label: str, path: str) -> None:
    """Log saved file paths without printing file contents."""
    print(f"{label}: {path}")


def build_document_body(spec_path: Optional[str],
                        spec_content: str,
                        branch_markdown: Dict[str, str]) -> str:
    """
    Build the combined specification + branch content section (without prompts).
    """
    parts: List[str] = []

    parts.append("# Specifications and design docs and prompts")
    parts.append("")

    if spec_content.strip():
        if spec_path:
            parts.append(f"_Source: `{spec_path}`_")
        parts.append("")
        parts.append(spec_content.rstrip())
        parts.append("")
    else:
        parts.append("_No specification was provided for this project._\n")

    for branch_name in branch_markdown:
        parts.append(f"# {branch_name} branch content")
        parts.append("")
        parts.append(branch_markdown[branch_name].rstrip())
        parts.append("")

    return "\n".join(parts)


def build_final_prompt(document_body: str, branch_names: List[str]) -> str:
    """
    Build the single, copy-paste-ready prompt (instructions + document body).
    The first line is the system-style instruction required by the user.
    """
    branches_display = ", ".join(f"`{name}`" for name in branch_names) if branch_names else "None"

    parts: List[str] = [
        INSTRUCTION_PROMPT,
        "",
        "Here is the combined specification and branch content markdown.",
        f"The branches to compare are: {branches_display}.",
        "",
        "---------------- BEGIN DOCUMENT ----------------",
        document_body.rstrip(),
        "---------------- END DOCUMENT ----------------",
    ]

    return "\n".join(parts)


# -----------------------
# Monitoring & main flow
# -----------------------

def monitor_branches(repo_path: str) -> Dict[str, BranchSpec]:
    """
    Poll remote branches on origin and ask the user which to evaluate.
    After adding each branch, the user can choose to start analysis right away,
    or keep waiting for more branches. Ctrl+C also proceeds to analysis.
    """
    selected: Dict[str, BranchSpec] = {}
    seen_branches: Set[str] = set()

    print(f"{CYAN}\nMonitoring origin for fresh branches...{RESET}")
    print(f"{DIM}Whenever something new lands, I'll ask whether to include it in the analysis.{RESET}")
    print(f"{DIM}Add branches as they appear, or jump into analysis at any time. Press Ctrl+C to stop watching.{RESET}\n")

    try:
        while True:
            try:
                run_git(repo_path, ["fetch", "origin", "--prune"])
            except Exception:
                # Already printed errors; wait and retry.
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            remote_branches = get_remote_branch_names(repo_path)
            new_branches = sorted(remote_branches - seen_branches)

            for branch in new_branches:
                print(f"{GREEN}●{RESET} {WHITE}New branch detected:{RESET} {DIM}{branch}{RESET}")
                add_prompt = (
                    f"{GREEN}●{RESET} {WHITE}Add branch{RESET} {DIM}'{branch}' to the evaluation set?{RESET}"
                )
                if ask_yes_no(add_prompt, default=True, suffix=f" {DIM}[Y/n]:{RESET} "):
                    selected[branch] = BranchSpec(name=branch)
                    print(f"{GREEN}✔{RESET} Added {DIM}{branch}{RESET} to the evaluation set.\n")

                    if ask_yes_no(
                        f"{GREEN}●{RESET} {WHITE}Start analysis now?{RESET} "
                        f"{DIM}(Otherwise I'll keep monitoring for more branches.){RESET}",
                        default=False,
                        suffix=f" {DIM}[yes / Enter for No]:{RESET} ",
                    ):
                        print(f"\n{CYAN}Starting analysis with the current set of branches...{RESET}\n")
                        return selected
                else:
                    print(f"{YELLOW}⏸  Skipping branch{RESET} {DIM}{branch}{RESET}.\n")
                    if ask_yes_no(
                        f"{GREEN}●{RESET} {WHITE}Would you like to start the analysis with the branches already tracked?{RESET}",
                        default=False,
                        suffix=f" {DIM}[yes / Enter for No]:{RESET} ",
                    ):
                        if selected:
                            print(f"\n{CYAN}Moving ahead to the analysis phase with existing selections...{RESET}\n")
                            return selected
                        print(f"{YELLOW}No branches are being tracked yet. Continuing to monitor.{RESET}\n")

            seen_branches = remote_branches

            if selected:
                tracked = ", ".join(sorted(selected.keys()))
                print(f"{WHITE}Currently tracking:{RESET} {DIM}{tracked}{RESET}")

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print(f"\n\n{CYAN}Stopping branch monitor and moving on to analysis...{RESET}\n")

    return selected


def main() -> None:
    print_banner()

    print(f"{WHITE}{BOLD}Welcome to multi-codex.{RESET} {DIM}Your branch comparison co-pilot for AI-generated solutions.{RESET}")
    print(f"{CYAN}Here's how we'll work together:{RESET}")
    print(f"  {GREEN}➊{RESET} Watch your GitHub repo for new branches as Codex ships them.")
    print(f"  {GREEN}➋{RESET} Capture your spec or prompt so we know what matters.")
    print(f"  {GREEN}➌{RESET} Turn each branch into a clean markdown snapshot.")
    print(f"  {GREEN}➍{RESET} Build a combined doc to paste into ChatGPT for a feature-by-feature verdict.\n")

    repo_url = input_non_empty(f"{WHITE}Enter your GitHub repository URL (HTTPS or SSH): {RESET}")

    spec_path, spec_content = prompt_for_project_spec()

    repo_slug = slugify_repo_url(repo_url)
    repo_path, report_path = ensure_app_dirs(repo_slug)

    ensure_local_clone(repo_url, repo_path)

    # Monitor new branches and let user choose which ones to evaluate
    branch_specs = monitor_branches(repo_path)

    if not branch_specs:
        print(f"{YELLOW}No branches were selected for evaluation. Exiting.{RESET}")
        return

    # Build per-branch markdowns
    print(f"{CYAN}Generating markdown snapshots for each selected branch...{RESET}\n")
    branch_markdown: Dict[str, str] = {}

    for branch_name, bs in branch_specs.items():
        print(f"{WHITE}Processing branch:{RESET} {DIM}{branch_name}{RESET}")
        md_text = collect_branch_markdown(repo_path, branch_name)
        branch_markdown[branch_name] = md_text

        branch_slug = slugify_branch_name(branch_name)
        branch_md_path = os.path.join(report_path, f"branch_{branch_slug}.md")
        with open(branch_md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        bs.branch_markdown_path = branch_md_path
        print_saved_file("  -> Branch markdown saved to", branch_md_path)

    document_body = build_document_body(spec_path, spec_content, branch_markdown)
    branch_names_sorted = sorted(branch_specs.keys())

    # Combined markdown prompt (ready to paste into AI UI)
    combined_prompt = build_final_prompt(document_body, branch_names_sorted)
    combined_prompt_path = os.path.join(report_path, "combined_spec_and_branches.md")

    with open(combined_prompt_path, "w", encoding="utf-8") as f:
        f.write(combined_prompt)

    print(f"\n{CYAN}Combined markdown saved to:{RESET}")
    print_saved_file(f"  {GREEN}→{RESET} Path", combined_prompt_path)
    print(f"  {DIM}(Contents intentionally not printed to avoid console noise){RESET}\n")

    print(f"{GREEN}Done ✅{RESET}")
    print(f"{WHITE}Next step:{RESET} Copy the contents of the combined file and paste them into ChatGPT for analysis.")
    print(f"{CYAN}Open ChatGPT:{RESET} https://chatgpt.com/")
    print(f"{DIM}Tip: paste the combined prompt into the chat UI to get the comparison report.{RESET}")
    print(f"\n{WHITE}You can open the markdown files in your editor to inspect:{RESET}")
    print_saved_file(f"  {GREEN}•{RESET} Combined specs + branches prompt", combined_prompt_path)
    print(f"\n{MAGENTA}Thank you for using multi-codex—happy comparing!{RESET}\n")


if __name__ == "__main__":
    main()
