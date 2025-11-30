from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from . import prompts

APP_DIR_NAME = ".multi_codex"
POLL_INTERVAL_SECONDS = 30
MAX_FILE_SIZE_BYTES = 200 * 1024
IGNORED_DIRS: Set[str] = {
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


class GitError(RuntimeError):
    """Represents a failure while running a git command."""

    def __init__(self, command: List[str], stderr: str | None = None):
        message = "Git command failed: " + " ".join(command)
        if stderr:
            message += f"\n{stderr.strip()}"
        super().__init__(message)
        self.command = command
        self.stderr = stderr or ""


@dataclass
class DiffResult:
    ok: bool
    has_changes: bool
    message: str
    diff_text: Optional[str] = None


@dataclass
class BranchSpec:
    name: str
    branch_markdown_path: Optional[str] = None


# -----------------------
# Git utilities
# -----------------------


def run_git(repo_path: str | Path, args: List[str]) -> str:
    """Run a git command in the given repo directory and return stdout."""

    cmd = ["git", "-C", str(repo_path)] + args
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment guard
        raise GitError(cmd, "'git' command not found. Please install Git and try again.") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(cmd, exc.stderr) from exc

    return result.stdout.strip()


def ensure_local_clone(repo_url: str, repo_path: str | Path) -> bool:
    """Ensure a local clone exists. Returns True if the repo already existed."""

    repo_path = Path(repo_path)
    if (repo_path / ".git").is_dir():
        run_git(repo_path, ["fetch", "origin", "--prune"])
        return True

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", repo_url, str(repo_path)]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment guard
        raise GitError(cmd, "'git' command not found. Please install Git and try again.") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(cmd, exc.stderr) from exc

    return False


def get_remote_branch_names(repo_path: str | Path) -> Set[str]:
    """Return a set of remote branch names (without the 'origin/' prefix)."""

    out = run_git(repo_path, ["branch", "-r", "--format", "%(refname:short)"])
    branches: Set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith("origin/"):
            continue
        name = line.split("/", 1)[1]
        if name == "HEAD":
            continue
        branches.add(name)

    return branches


# -----------------------
# File helpers
# -----------------------


def slugify_repo_url(url: str) -> str:
    """Convert a GitHub repository URL into a filesystem-friendly slug."""

    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]

    if url.startswith("git@"):
        after_colon = url.split(":", 1)[1]
        path_part = after_colon.strip("/")
    else:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path_part = (parsed.path or "").lstrip("/")

    if not path_part:
        return "unknown_repo"

    return path_part.replace("/", "_").replace(".", "_").lower()


def ensure_app_dirs(repo_slug: str) -> tuple[Path, Path]:
    """Create/return the app directories for repos and reports."""

    home = Path.home()
    app_root = home / APP_DIR_NAME
    repos_root = app_root / "repos"
    reports_root = app_root / "reports"
    repos_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    repo_path = repos_root / repo_slug
    report_path = reports_root / repo_slug
    report_path.mkdir(exist_ok=True)
    return repo_path, report_path


def is_binary_content(sample: bytes) -> bool:
    """Detect binary file by presence of NULL byte in a sample."""

    return b"\0" in sample


def read_text_file(path: str | Path) -> Optional[str]:
    """Read a file as text, skipping binary and very large files."""

    path = Path(path)
    try:
        size = path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            return None

        with path.open("rb") as f:
            sample = f.read(4096)
            if is_binary_content(sample):
                return None

        with path.open("r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with path.open("r", encoding="latin-1") as f:
                return f.read()
        except Exception:
            return None
    except Exception:
        return None


def guess_language_from_path(path: str | Path) -> str:
    """Infer a markdown code fence language from a file path."""

    path_str = str(path)
    for ext, lang in LANGUAGE_EXTENSIONS.items():
        if path_str.endswith(ext):
            return lang
    return ""


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
    """Convert a branch name into a filesystem-friendly slug."""

    return (
        branch_name.replace("/", "_")
        .replace(" ", "_")
        .replace("#", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def sync_remote_branch(repo_path: str | Path, branch_name: str) -> None:
    """Ensure a local branch tracks origin/<branch_name>."""

    run_git(repo_path, ["fetch", "origin", "--prune"])
    run_git(repo_path, ["checkout", "-q", "-B", branch_name, f"origin/{branch_name}"])


def collect_branch_markdown(repo_path: str | Path, branch_name: str) -> str:
    """Check out a branch and turn all (reasonable) files into a big markdown document."""

    sync_remote_branch(repo_path, branch_name)

    repo_path = Path(repo_path)
    repo_name = repo_path.name
    file_entries: List[Dict[str, str]] = []

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and d != APP_DIR_NAME]

        for file_name in sorted(files):
            full_path = Path(root) / file_name
            rel_path = str(full_path.relative_to(repo_path))
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


# -----------------------
# Prompt builders
# -----------------------


def build_single_branch_prompt(prompt_name: str, branch_markdown: str) -> str:
    """Assemble a single-branch document with a system prompt header."""

    system_prompt = prompts.load_prompt(prompt_name)
    return "\n".join(
        [
            system_prompt.strip(),
            "",
            "---------------- BEGIN DOCUMENT ----------------",
            branch_markdown.rstrip(),
            "---------------- END DOCUMENT ----------------",
        ]
    )


def build_document_body(
    spec_path: Optional[str], spec_content: str, branch_markdown: Dict[str, str]
) -> str:
    """Build the combined specification + branch content section (without prompts)."""

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

    for branch_name, markdown in branch_markdown.items():
        parts.append(f"# {branch_name} branch content")
        parts.append("")
        parts.append(markdown.rstrip())
        parts.append("")

    return "\n".join(parts)


def build_final_prompt(document_body: str, branch_names: List[str]) -> str:
    """Build the combined prompt for branch comparison."""

    system_prompt = prompts.load_prompt("branch_comparison")
    branches_display = ", ".join(f"`{name}`" for name in branch_names) if branch_names else "None"

    parts: List[str] = [
        system_prompt.strip(),
        "",
        "Here is the combined specification and branch content markdown.",
        f"The branches to compare are: {branches_display}.",
        "",
        "---------------- BEGIN DOCUMENT ----------------",
        document_body.rstrip(),
        "---------------- END DOCUMENT ----------------",
    ]

    return "\n".join(parts)


def compute_branch_diff(
    repo_path: str | Path, branch_name: str, base_branch: str = "main"
) -> DiffResult:
    """Return the git diff between the PR branch and the base branch."""

    try:
        run_git(repo_path, ["fetch", "origin", "--prune"])
    except GitError as exc:
        return DiffResult(False, False, f"Failed to fetch from origin: {exc}")

    branch_ref = f"origin/{branch_name}"
    base_ref = f"origin/{base_branch}"

    def ref_exists(ref: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.returncode == 0

    missing_refs = [ref for ref in (base_ref, branch_ref) if not ref_exists(ref)]
    if missing_refs:
        missing_list = ", ".join(missing_refs)
        return DiffResult(
            False,
            False,
            (
                "Unable to compute diff because the following references were not found on origin: "
                f"{missing_list}. Please ensure the branch names are correct and fetched."
            ),
        )

    try:
        diff_output = run_git(repo_path, ["diff", f"{base_ref}...{branch_ref}"])
    except GitError as exc:
        return DiffResult(
            False,
            False,
            f"Failed to compute diff between {branch_ref} and {base_ref}: {exc}",
        )

    if not diff_output.strip():
        return DiffResult(True, False, f"No differences between {branch_ref} and {base_ref}.", "")

    return DiffResult(True, True, "", diff_output.strip())


def build_pr_mega_prompt(
    repo_path: str | Path,
    branch_name: str,
    base_branch: str = "main",
) -> str:
    """Combine long context and git diff into a single PR analysis prompt."""

    system_prompt = prompts.load_prompt("pr_long_context")
    branch_markdown = collect_branch_markdown(repo_path, branch_name)
    diff_result = compute_branch_diff(repo_path, branch_name, base_branch)

    if diff_result.ok and diff_result.has_changes and diff_result.diff_text:
        diff_block = ["```diff", diff_result.diff_text.strip(), "```"]
    else:
        header = "Diff computation error" if not diff_result.ok else "No diff to show"
        content = diff_result.message or "No differences were detected."
        diff_block = ["```text", f"{header}: {content}", "```"]

    parts: List[str] = [
        system_prompt.strip(),
        "",
        "---------------- BEGIN DOCUMENT ----------------",
        f"## PR Branch Long Context ({branch_name})",
        branch_markdown.rstrip(),
        "",
        f"## Diff: {branch_name} vs {base_branch}",
        *diff_block,
        "---------------- END DOCUMENT ----------------",
    ]

    return "\n".join(parts)


def build_architecture_report(repo_path: str | Path, branch_name: str) -> str:
    """Generate the architecture deep-dive prompt for a branch."""

    branch_markdown = collect_branch_markdown(repo_path, branch_name)
    return build_single_branch_prompt("arch_deep_dive", branch_markdown)


def build_feature_security_analysis(repo_path: str | Path, branch_name: str) -> str:
    """Generate the feature, security, and modernization analysis prompt for a branch."""

    branch_markdown = collect_branch_markdown(repo_path, branch_name)
    return build_single_branch_prompt("feature_security_analysis", branch_markdown)


__all__ = [
    "APP_DIR_NAME",
    "BranchSpec",
    "DiffResult",
    "IGNORED_DIRS",
    "MAX_FILE_SIZE_BYTES",
    "POLL_INTERVAL_SECONDS",
    "ensure_app_dirs",
    "ensure_local_clone",
    "get_remote_branch_names",
    "slugify_repo_url",
    "slugify_branch_name",
    "collect_branch_markdown",
    "build_architecture_report",
    "build_feature_security_analysis",
    "build_pr_mega_prompt",
    "build_document_body",
    "build_final_prompt",
    "build_single_branch_prompt",
    "compute_branch_diff",
    "run_git",
]
