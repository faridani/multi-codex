import os
import subprocess
from pathlib import Path

import pytest

from multi_codex import core


class DummyResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_slugify_repo_url_variants():
    assert core.slugify_repo_url("https://github.com/openai/example.git") == "openai_example"
    assert core.slugify_repo_url("git@github.com:OpenAI/example") == "openai_example"
    assert core.slugify_repo_url("https://github.com/openai/example") == "openai_example"


def test_ensure_app_dirs_creates_structure(temp_home):
    repo_path, report_path = core.ensure_app_dirs("my_repo")

    assert repo_path == temp_home / ".multi_codex" / "repos" / "my_repo"
    assert report_path == temp_home / ".multi_codex" / "reports" / "my_repo"
    assert repo_path.is_dir()
    assert report_path.is_dir()


def test_read_text_file_handles_text_binary_and_size_limits(tmp_path):
    text_file = tmp_path / "example.txt"
    text_file.write_text("hello world", encoding="utf-8")
    assert core.read_text_file(text_file) == "hello world"

    binary_file = tmp_path / "binary.bin"
    binary_file.write_bytes(b"\x00\x01\x02")
    assert core.read_text_file(binary_file) is None

    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"a" * (core.MAX_FILE_SIZE_BYTES + 1))
    assert core.read_text_file(large_file) is None


def test_guess_language_from_path_recognizes_extensions():
    assert core.guess_language_from_path("file.py") == "python"
    assert core.guess_language_from_path("notes.md") == "markdown"
    assert core.guess_language_from_path("unknown.xyz") == ""


def test_build_tree_from_paths_orders_directories():
    tree = core.build_tree_from_paths(
        "repo",
        [
            os.path.join("src", "main.py"),
            os.path.join("README.md"),
            os.path.join("src", "utils", "helpers.py"),
        ],
    )

    expected_lines = [
        "repo",
        "├── src",
        "│   ├── utils",
        "│   │   └── helpers.py",
        "│   └── main.py",
        "└── README.md",
    ]
    assert tree.splitlines() == expected_lines


def test_slugify_branch_name_replaces_special_characters():
    assert core.slugify_branch_name("feature/ABC-123 fix#1") == "feature_ABC-123_fix_1"


def test_build_document_body_includes_spec_and_branches():
    branch_markdown = {"main": "MAIN", "dev": "DEV"}

    body = core.build_document_body("spec.md", "SPEC CONTENT", branch_markdown)

    assert "SPEC CONTENT" in body
    assert "# main branch content" in body
    assert "DEV" in body


def test_build_branch_comparison_prompt_assembles_sections(monkeypatch):
    monkeypatch.setattr(core.prompts, "load_prompt", lambda name: "SYSTEM PROMPT")
    branch_markdown = {"feature": "Feature markdown"}

    prompt = core.build_branch_comparison_prompt("spec.md", "SPEC", branch_markdown)

    assert prompt.startswith("SYSTEM PROMPT")
    assert "Feature markdown" in prompt
    assert "spec.md" in prompt


def test_compute_branch_diff_missing_refs(monkeypatch):
    monkeypatch.setattr(core, "run_git", lambda repo, args: "")

    def fake_run(cmd, **kwargs):
        if "show-ref" in cmd:
            return DummyResult(returncode=1)
        return DummyResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = core.compute_branch_diff("/tmp/repo", "feature", base_branch="main")

    assert not result.ok
    assert "origin/main" in result.message


def test_compute_branch_diff_with_and_without_changes(monkeypatch):
    calls = []

    def fake_run_git(repo_path, args):
        calls.append(args)
        if args[0] == "diff":
            return "diff output" if "feature" in args[-1] else ""
        return ""

    monkeypatch.setattr(core, "run_git", fake_run_git)

    def fake_run(cmd, **kwargs):
        if "show-ref" in cmd:
            return DummyResult(returncode=0)
        return DummyResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    diff_result = core.compute_branch_diff("/tmp/repo", "feature", base_branch="main")
    assert diff_result.ok
    assert diff_result.has_changes
    assert diff_result.diff_text == "diff output"

    # Now simulate no diff output
    calls.clear()

    def fake_run_git_no_diff(repo_path, args):
        if args[0] == "diff":
            return ""
        return ""

    monkeypatch.setattr(core, "run_git", fake_run_git_no_diff)
    diff_result_no_changes = core.compute_branch_diff("/tmp/repo", "feature", base_branch="main")
    assert diff_result_no_changes.ok
    assert not diff_result_no_changes.has_changes
    assert "No differences" in diff_result_no_changes.message
