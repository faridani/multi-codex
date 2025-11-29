#!/usr/bin/env python3
"""
multi_codex.py

Mac CLI tool to:
- Watch a GitHub repo for new branches (using your existing git/GitHub auth).
- Ask which branches to evaluate and where your specification doc lives.
- Generate markdown snapshots of each branch (file names + contents).
- Build a combined markdown file with specs + branches that you can paste
  into an AI UI to get a comparison table of features vs. branches.

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
import shutil
import textwrap
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

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".md": "markdown",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
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

COLOR = {
    "green": "\033[32m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "yellow": "\033[33m",
    "grey": "\033[90m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

INSTRUCTION_PROMPT = (
    "You are an expert software architect and evaluator.\n"
    "You will receive a combined markdown document that contains:\n"
    "1) Specifications, design docs, or prompts.\n"
    "2) Several GitHub branches, including file paths and file contents.\n"
    "\n"
    "Your mission:\n"
    "- Derive a clear checklist of the features/requirements from the specification section.\n"
    "- Create a MARKDOWN TABLE where:\n"
    "  - Rows are the features.\n"
    "  - Columns are the branch names.\n"
    "  - Each cell is 'Yes' or 'No' based strictly on evidence in the branch content. Avoid speculation.\n"
    "- After the table, provide:\n"
    "  1) A concise rationale for which branch is best.\n"
    "  2) The single best branch name.\n"
    "  3) The features the best branch is missing or only partially implements.\n"
    "Be crisp and evidence-driven."
)

AI_PROMPT_CONFIG: Dict[str, str] = {
    "branch_comparison": INSTRUCTION_PROMPT,
    "arch_deep_dive": textwrap.dedent(
        """
        You are a skilled and experienced **Software Architect** consultant. Your primary task is to analyze the provided documentation, file structure, and code content from a software branch and generate a comprehensive, professional **Architectural Report**.

        Your analysis must be grounded strictly in the provided content. Assume the perspective of a technical leader presenting findings to a team of engineers and stakeholders.

        The final report must be clearly structured and must address all of the following requirements in detail:

        ### 1. Software Overview & Functionality

        * **Core Purpose:** Explain the software's primary objective and what problem it is designed to solve.
        * **Functionality:** Describe the key features and observable actions the software performs, as evidenced by the code (e.g., API endpoints, database models, UI components).

        ### 2. Technology Stack Deep Dive

        * **Identification:** List all identified programming **languages**, major **frameworks** (e.g., FastAPI, React, Django), and key **libraries/tools** (e.g., SQLAlchemy, pytest) used in the project.
        * **Architectural Context and Assessment:** For each significant technology, analyze its use within the project's architecture and detail the relevant **pros and cons** (advantages/disadvantages) of using that specific technology for this kind of software.

        ### 3. Component Breakdown & Detailed Code Explanation

        * **Architecture Components:** Identify and describe the major architectural components (e.g., data models, authentication layer, API routes, testing structure, frontend views).
        * **In-Depth Code Analysis:** For each critical or representative piece of code (e.g., a specific class, function, or file), provide a detailed explanation of its purpose, logic flow, and implementation details. This explanation must be technical enough for a person with strong familiarity with the coding language and the used technologies to fully understand *how* it works and *why* it was implemented that way.

        ### 4. Code Quality Assessment (Strengths)

        * **Well-Coded Areas:** Identify specific files, functions, or architectural decisions that demonstrate **excellent** coding practices, adherence to design patterns, efficiency, strong abstraction, or robust testing (if applicable).
        * **Justification:** Explain precisely *why* these areas are considered well-coded.

        ### 5. Technical Debt and Improvement Areas (Weaknesses)

        * **Areas for Improvement:** Identify specific files, functions, or architectural patterns that require attention.
        * **Recommendations:** Provide specific, actionable recommendations for improvement, categorized as:
            * **Architectural Flaws:** Suggestions for better design patterns, decoupling, or scaling.
            * **Performance Bottlenecks:** Areas that may be slow or resource-intensive.
            * **Security Risks:** Potential vulnerabilities (e.g., data handling, API key storage, input validation).
            * **Maintainability/Readability:** Complex, overly-coupled, poorly documented, or non-idiomatic code that increases long-term cost.

        ### 6. Summary and Conclusion

        * Provide a concise executive summary of the software's overall architectural health and strategic next steps.
        """
    ).strip(),  # NOTE: Original spec text included the typo "architech"; the prompt intentionally corrects it.
    "feature_security_analysis": textwrap.dedent(
        """
        You are a **Senior Software Engineer and Technical Consultant** with extensive experience in code auditing, security analysis, and product development.

        Your task is to review the provided code branch and produce a **Strategic Code Review and Roadmap**. You must look beyond simple syntax checks and analyze the codebase from the perspective of security, scalability, maintainability, and product evolution.

        Please structure your response into the following detailed sections:

        ### 1. System Summary & Codebase Orientation
        * **Context:** Briefly explain what this software appears to be doing based on the file structure and code logic.
        * **Tech Stack:** Identify the core languages, frameworks, and libraries in use.

        ### 2. Security & Safety Audit (Critical)
        * **Vulnerability Analysis:** Scrutinize the code for common security flaws (e.g., SQL injection, XSS, hardcoded secrets, improper authentication/authorization, insecure dependency usage).
        * **Data Safety:** Analyze how user input is validated and sanitized.
        * **Risk Assessment:** Flag any "unsafe" operations (e.g., shell execution, unchecked file system access) and rate their severity (High/Medium/Low).

        ### 3. Code Quality & "Flimsiness" Assessment
        * **Fragility Analysis:** Identify areas of the code that appear "flimsy" or brittle—sections that are likely to break with minor changes or unexpected input.
        * **Error Handling:** Evaluate the robustness of error handling. Are exceptions swallowed? Are error messages informative?
        * **Anti-Patterns:** Point out specific coding anti-patterns, spaghetti code, or highly coupled components that hinder maintainability.

        ### 4. Modernization & Refactoring Roadmap
        * **Technical Debt:** Highlight legacy code structures or outdated libraries that should be upgraded.
        * **Performance:** Suggest optimizations for loops, database queries, or resource-heavy operations.
        * **Best Practices:** Recommend modern language features or architectural patterns (e.g., moving to async/await, using dependency injection, implementing strong typing) that would improve the codebase.

        ### 5. Testing Strategy & Gap Analysis
        * **Current State:** Assess existing tests (if any).
        * **Proposed Test Cases:** Suggest specific **Unit Tests** for complex logic, **Integration Tests** for API endpoints or database interactions, and **Edge Case** scenarios that the developer might have missed.

        ### 6. Feature Proposals & Product Evolution
        * **Logical Extensions:** Based on the current functionality, suggest 3-5 new features that would add significant value to the user or admin experience.
        * **Developer Experience:** Suggest tooling or scripts that could make working on this repository easier (e.g., linters, pre-commit hooks, Dockerization).
        """
    ).strip(),
    "pr_long_context": textwrap.dedent(
        """
        You are a senior engineer preparing a Pull Request review. You will receive two sources of truth:

        1) A "long context" snapshot of the PR branch that includes the project structure and the full contents of relevant files.
        2) A Git diff showing every change between the PR branch and the base branch.

        How to use this information:
        - Treat the long context as the authoritative view of the branch in its current state.
        - Use the diff to understand what changed from the base branch and to focus your review on the new work.

        Deliverables:
        1) A concise summary of the PR changes grounded in the diff.
        2) A risk and impact assessment that references specific files or code paths.
        3) Targeted review notes highlighting potential bugs, gaps in tests, or architectural concerns.
        4) A clear list of follow-up actions or questions for the author.
        """
    ).strip(),
}


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
    """Print a nice banner."""
    print(color_text(BANNER, "cyan"))


def input_non_empty(prompt: str) -> str:
    """Prompt until user provides a non-empty response."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Please enter a non-empty value.\n")


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


def choose_from_list(options: List[str], prompt: str) -> str:
    """Prompt the user to select from a numbered list of options."""
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
    """Allow branch selection by index or name with validation."""
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


def prompt_for_branch_selection(repo_path: str, action_label: str) -> str:
    """Ask the user to pick a branch from the remote list for a single-branch workflow."""
    run_git(repo_path, ["fetch", "origin", "--prune"])
    branches = sorted(get_remote_branch_names(repo_path))

    if not branches:
        print("No remote branches found on origin. Exiting.")
        sys.exit(1)

    choice = select_branch(branches, f"Select the branch to {action_label}:")
    if choice is None:
        print("No branch selected. Exiting.")
        sys.exit(1)

    return choice


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


def guess_language_from_path(path: str) -> str:
    """Infer a markdown code fence language from a file path."""
    ext = os.path.splitext(path)[1].lower()
    return LANGUAGE_EXTENSIONS.get(ext, "")


def build_tree_from_paths(repo_name: str, paths: List[str]) -> str:
    """Create an ASCII directory tree for the provided file paths."""

    def insert_path(tree: Dict[str, Dict], path: str) -> None:
        parts = path.split(os.sep)
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None

    def render_tree(tree: Dict[str, Dict], prefix: str = "") -> List[str]:
        rendered: List[str] = []
        entries = sorted(tree.items(), key=lambda item: (item[1] is None, item[0].lower()))
        for idx, (name, child) in enumerate(entries):
            connector = "└── " if idx == len(entries) - 1 else "├── "
            rendered.append(f"{prefix}{connector}{name}")
            if isinstance(child, dict):
                extension = "    " if idx == len(entries) - 1 else "│   "
                rendered.extend(render_tree(child, prefix + extension))
        return rendered

    tree: Dict[str, Dict] = {}
    for path in paths:
        insert_path(tree, path)

    lines = [repo_name]
    lines.extend(render_tree(tree))
    return "\n".join(lines)


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

    repo_name = os.path.basename(os.path.abspath(repo_path))
    file_entries: List[Dict[str, str]] = []

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and d != APP_DIR_NAME]

        for file_name in sorted(files):
            full_path = os.path.join(root, file_name)
            rel_path = os.path.relpath(full_path, repo_path)

            text = read_text_file(full_path)
            if text is None:
                continue

            file_entries.append(
                {
                    "path": rel_path,
                    "content": text.rstrip(),
                    "language": guess_language_from_path(rel_path),
                }
            )

    file_entries.sort(key=lambda entry: entry["path"].lower())
    tree_paths = [entry["path"] for entry in file_entries]
    tree = build_tree_from_paths(repo_name, tree_paths) if tree_paths else repo_name

    lines: List[str] = []
    lines.append(f"# Project: {repo_name} (Branch: {branch_name})")
    lines.append("")
    lines.append("## Project Structure")
    lines.append("```")
    lines.append(tree)
    lines.append("```")
    lines.append("---")
    lines.append("## File Contents")

    for entry in file_entries:
        lang = entry["language"]
        fence = f"```{lang}" if lang else "```"
        lines.append(f"### FILE: {entry['path']}")
        lines.append(fence)
        lines.append(entry["content"])
        lines.append("```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_single_branch_prompt(system_prompt: str, branch_markdown: str) -> str:
    """Assemble a single-branch document with a system prompt header."""
    return "\n".join(
        [
            system_prompt.strip(),
            "",
            "---------------- BEGIN DOCUMENT ----------------",
            branch_markdown.rstrip(),
            "---------------- END DOCUMENT ----------------",
        ]
    )


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
        AI_PROMPT_CONFIG["branch_comparison"],
        "",
        "Here is the combined specification and branch content markdown.",
        f"The branches to compare are: {branches_display}.",
        "",
        "---------------- BEGIN DOCUMENT ----------------",
        document_body.rstrip(),
        "---------------- END DOCUMENT ----------------",
    ]

    return "\n".join(parts)


def compute_branch_diff(repo_path: str, branch_name: str, base_branch: str = "main") -> str:
    """Return the git diff between the PR branch and the base branch."""
    run_git(repo_path, ["fetch", "origin", "--prune"])

    branch_ref = f"origin/{branch_name}"
    base_ref = f"origin/{base_branch}"
    diff_output = run_git(repo_path, ["diff", f"{base_ref}...{branch_ref}"])

    if not diff_output.strip():
        return f"No differences between {branch_ref} and {base_ref}."

    return diff_output.strip()


def build_pr_mega_prompt(system_prompt: str,
                        branch_name: str,
                        base_branch: str,
                        branch_markdown: str,
                        diff_text: str) -> str:
    """Combine long context and git diff into a single PR analysis prompt."""
    diff_body = diff_text.strip() or f"No differences between origin/{branch_name} and origin/{base_branch}."

    parts: List[str] = [
        system_prompt.strip(),
        "",
        "---------------- BEGIN DOCUMENT ----------------",
        f"## PR Branch Long Context ({branch_name})",
        branch_markdown.rstrip(),
        "",
        f"## Diff: {branch_name} vs {base_branch}",
        "```diff",
        diff_body,
        "```",
        "---------------- END DOCUMENT ----------------",
    ]

    return "\n".join(parts)


def copy_to_clipboard(text: str) -> bool:
    """
    Attempt to copy text to the clipboard on macOS, Windows, or Linux.
    Returns True if successful.
    """
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
        # Windows built-in clipboard command
        if shutil.which("clip") is None:
            return False
        try:
            subprocess.run(["clip"], input=text, text=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    if platform.startswith("linux"):
        # Prefer wl-copy (Wayland), fall back to xclip (X11)
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
                run_git(repo_path, ["fetch", "origin", "--prune"])
            except Exception:
                # Already printed errors; wait and retry.
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            remote_branches = get_remote_branch_names(repo_path)
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

    repo_slug = slugify_repo_url(repo_url)
    repo_path, report_path = ensure_app_dirs(repo_slug)

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
        branch_markdown = collect_branch_markdown(repo_path, branch_name)
        combined_prompt = build_single_branch_prompt(
            AI_PROMPT_CONFIG["arch_deep_dive"], branch_markdown
        )

        branch_slug = slugify_branch_name(branch_name)
        output_path = os.path.join(report_path, f"architecture_report_{branch_slug}.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined_prompt)

        print_saved_file("Architectural report prompt saved to", output_path)
        if copy_to_clipboard(combined_prompt):
            print(color_text("  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.", "green"))
        else:
            print(color_text("  • Copy the report from the path above to share with your AI assistant.", "yellow"))

    elif selected_option == options[1]:
        spec_path, spec_content = prompt_for_project_spec()

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
            print_saved_file("  -> Branch markdown saved to", branch_md_path)

        document_body = build_document_body(spec_path, spec_content, branch_markdown)
        branch_names_sorted = sorted(branch_specs.keys())

        # Combined markdown prompt (ready to paste into AI UI)
        combined_prompt = build_final_prompt(document_body, branch_names_sorted)
        combined_prompt_path = os.path.join(report_path, "combined_spec_and_branches.md")

        with open(combined_prompt_path, "w", encoding="utf-8") as f:
            f.write(combined_prompt)

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
        branch_name = prompt_for_branch_selection(
            repo_path, "convert to long context and diff for PR review"
        )
        base_branch_input = input("Enter the base branch to diff against [main]: ").strip()
        base_branch = base_branch_input or "main"

        print(f"\nBuilding long-context snapshot for PR branch: {branch_name}\n")
        branch_markdown = collect_branch_markdown(repo_path, branch_name)

        print(f"Computing diff against base branch '{base_branch}'...\n")
        diff_text = compute_branch_diff(repo_path, branch_name, base_branch)

        combined_prompt = build_pr_mega_prompt(
            AI_PROMPT_CONFIG["pr_long_context"],
            branch_name,
            base_branch,
            branch_markdown,
            diff_text,
        )

        branch_slug = slugify_branch_name(branch_name)
        base_slug = slugify_branch_name(base_branch)
        output_path = os.path.join(
            report_path, f"pr_review_prompt_{branch_slug}_vs_{base_slug}.md"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined_prompt)

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
        branch_markdown = collect_branch_markdown(repo_path, branch_name)
        combined_prompt = build_single_branch_prompt(
            AI_PROMPT_CONFIG["feature_security_analysis"], branch_markdown
        )

        branch_slug = slugify_branch_name(branch_name)
        output_path = os.path.join(report_path, f"feature_security_report_{branch_slug}.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined_prompt)

        print_saved_file("Feature and security report saved to", output_path)
        if copy_to_clipboard(combined_prompt):
            print(color_text("  • Prompt copied. Upload the saved file or paste into your AI and ask it to follow the file instructions.", "green"))
        else:
            print(color_text("  • Copy the report from the path above to share with your AI assistant.", "yellow"))

    if selected_option != options[1]:
        print(color_text("\nDone ✅", "green", bold=True))
        print(color_text("You can open the markdown file in your editor or share it with your AI assistant.", "grey"))
        print(color_text("\nThank you for using multi-codex.\n", "cyan", bold=True))


if __name__ == "__main__":
    main()
