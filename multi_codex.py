#!/usr/bin/env python3
"""
multi_codex.py

Mac CLI tool to:
- Watch a GitHub repo for new branches (using your existing git/GitHub auth).
- Ask which branches to evaluate and where your specification doc lives.
- Generate markdown snapshots of each branch (file names + contents).
- Build a combined markdown file with specs + branches.
- Call the OpenAI API to produce a feature vs. branch comparison table
  and recommend the best branch.

Requirements:
- Python 3.9+
- git installed and configured (so that it can access your private repos)
- pip install openai

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

BANNER = r"""
░███     ░███            ░██    ░██    ░██                             ░██                       
░████   ░████            ░██    ░██                                    ░██                       
░██░██ ░██░██ ░██    ░██ ░██ ░████████ ░██ ░███████   ░███████   ░████████  ░███████  ░██    ░██ 
░██ ░████ ░██ ░██    ░██ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██  ░██  ░██  
░██  ░██  ░██ ░██    ░██ ░██    ░██    ░██░██        ░██    ░██ ░██    ░██ ░█████████   ░█████   
░██       ░██ ░██   ░███ ░██    ░██    ░██░██    ░██ ░██    ░██ ░██   ░███ ░██         ░██  ░██  
░██       ░██  ░█████░██ ░██     ░████ ░██ ░███████   ░███████   ░█████░██  ░███████  ░██    ░██ 
                                                                                                 
                                                                                                 
                                                                                                 

Multi-branch code evaluator for GitHub repos using OpenAI.
"""


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


def input_non_empty(prompt: str) -> str:
    """Prompt until user provides a non-empty response."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Please enter a non-empty value.\n")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """
    Ask a yes/no question.

    Returns True for yes, False for no.
    """
    suffix = " [Y/n]: " if default else " [y/N]: "
    full_prompt = prompt.rstrip() + suffix
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
    - ~/.multi_codex/reports/<slug> (markdown + OpenAI report)
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

    if result.stdout.strip():
        print(result.stdout.strip())


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


def build_combined_markdown(spec_path: Optional[str],
                            spec_content: str,
                            branch_markdown: Dict[str, str]) -> str:
    """
    Build the final combined markdown file you described:

    # specifications and design docs and prompts
    ...
    # branch 1 name and content
    ...
    # branch 2 name and content
    ...
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


# -----------------------
# OpenAI integration
# -----------------------

def generate_openai_report(combined_markdown: str,
                           branch_names: List[str]) -> str:
    """
    Call the OpenAI API to analyze which branch implements which features,
    and select the best branch.

    Expects OPENAI_API_KEY to be set in environment.
    """
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError:
        print("\nError: The 'openai' package is not installed.", file=sys.stderr)
        print("Install it with: pip install openai\n", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\nError: OPENAI_API_KEY is not set in your environment.", file=sys.stderr)
        print("Set it with something like:", file=sys.stderr)
        print("  export OPENAI_API_KEY='sk-...'\n", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    branches_display = ", ".join(f"`{name}`" for name in branch_names)

    system_message = (
        "You are an expert software architect. "
        "You will be given a combined markdown document that contains:\n"
        "1) Specifications / design docs / prompts.\n"
        "2) Multiple branches of a GitHub repository, including file paths and file contents.\n\n"
        "Your tasks:\n"
        "- Infer a clear list of key features/requirements from the specification section.\n"
        "- Construct a MARKDOWN TABLE where:\n"
        "  - Rows are features.\n"
        "  - Columns are the branch names.\n"
        "  - Each cell is 'Yes' or 'No' indicating whether that branch implements that feature.\n"
        "- Base your answer on the branch contents – do not speculate without evidence.\n"
        "- After the table, write:\n"
        "  1) A short explanation of how you chose the 'best' branch.\n"
        "  2) Explicitly name the single best branch.\n"
        "  3) List the features that the best branch is still missing or only partially implements.\n"
        "Use concise language."
    )

    user_message = (
        "Here is the combined specification and branch content markdown.\n"
        f"The branches to compare are: {branches_display}.\n\n"
        "---------------- BEGIN DOCUMENT ----------------\n"
        f"{combined_markdown}\n"
        "---------------- END DOCUMENT ----------------\n"
    )

    print("Calling OpenAI API to generate comparison report...")

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )
    except Exception as e:  # noqa: BLE001
        print(f"\nError while calling OpenAI API: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        content = completion.choices[0].message.content
    except Exception:
        content = str(completion)

    return content or ""


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

    print("\nMonitoring remote branches on 'origin'.")
    print("Whenever a new branch appears, you'll be asked if you want to track it.")
    print("After adding a branch you can start analysis immediately or keep waiting for more.")
    print("Press Ctrl+C when you're ready to stop monitoring and generate the report.\n")

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
                print(f"New branch detected: {branch}")
                if ask_yes_no(f"Add branch '{branch}' to the evaluation set?", default=True):
                    selected[branch] = BranchSpec(name=branch)
                    print(f"Branch '{branch}' added to evaluation set.\n")

                    if ask_yes_no(
                        "Start analysis now? (Otherwise I'll keep monitoring for more branches.)",
                        default=False,
                    ):
                        print("\nStarting analysis with the current set of branches...\n")
                        return selected
                else:
                    print(f"Skipping branch '{branch}'.\n")

            seen_branches = remote_branches

            if selected:
                tracked = ", ".join(sorted(selected.keys()))
                print(f"Currently tracking branches: {tracked}")

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n\nStopping branch monitor and moving on to analysis...\n")

    return selected


def main() -> None:
    print_banner()

    print("Welcome to multi-codex.")
    print("This tool will:")
    print("  1) Monitor a GitHub repository for new branches.")
    print("  2) Ask which branches to evaluate and where your spec lives.")
    print("  3) Generate markdown files for each branch.")
    print("  4) Build a combined markdown with specs + branches.")
    print("  5) Ask OpenAI which branch best matches the spec.\n")

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set in your environment.")
        print("Please run: export OPENAI_API_KEY='sk-...'\nThen re-run multi-codex.")
        sys.exit(1)

    repo_url = input_non_empty("Enter your GitHub repository URL (HTTPS or SSH): ")

    spec_path, spec_content = prompt_for_project_spec()

    repo_slug = slugify_repo_url(repo_url)
    repo_path, report_path = ensure_app_dirs(repo_slug)

    ensure_local_clone(repo_url, repo_path)

    # Monitor new branches and let user choose which ones to evaluate
    branch_specs = monitor_branches(repo_path)

    if not branch_specs:
        print("No branches were selected for evaluation. Exiting.")
        return

    # Build per-branch markdowns
    print("Generating markdown snapshot for each selected branch...\n")
    branch_markdown: Dict[str, str] = {}

    for branch_name, bs in branch_specs.items():
        print(f"Processing branch: {branch_name}")
        md_text = collect_branch_markdown(repo_path, branch_name)
        branch_markdown[branch_name] = md_text

        branch_slug = slugify_branch_name(branch_name)
        branch_md_path = os.path.join(report_path, f"branch_{branch_slug}.md")
        with open(branch_md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        bs.branch_markdown_path = branch_md_path
        print(f"  -> Branch markdown saved to: {branch_md_path}")

    # Combined markdown
    combined_md = build_combined_markdown(spec_path, spec_content, branch_markdown)
    combined_md_path = os.path.join(report_path, "combined_spec_and_branches.md")

    with open(combined_md_path, "w", encoding="utf-8") as f:
        f.write(combined_md)

    print(f"\nCombined markdown saved to:\n  {combined_md_path}\n")

    # Call OpenAI to get the comparison table and best branch
    branch_names_sorted = sorted(branch_specs.keys())
    report_text = generate_openai_report(combined_md, branch_names_sorted)

    report_path_md = os.path.join(report_path, "openai_branch_comparison_report.md")
    with open(report_path_md, "w", encoding="utf-8") as f:
        f.write(report_text)

    print("OpenAI comparison report saved to:")
    print(f"  {report_path_md}\n")

    print("Done ✅")
    print("You can open the markdown files in your editor to inspect:")
    print(f"  - Combined specs + branches : {combined_md_path}")
    print(f"  - OpenAI comparison report  : {report_path_md}")
    print("\nThank you for using multi-codex.\n")


if __name__ == "__main__":
    main()
