import subprocess
from pathlib import Path

import pytest

from multi_codex import core, prompts


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a working clone backed by a bare origin repo."""

    origin = tmp_path / "origin.git"
    workdir = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True)
    subprocess.run(["git", "clone", str(origin), str(workdir)], check=True)

    subprocess.run(
        ["git", "-C", str(workdir), "config", "user.email", "you@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(workdir), "config", "user.name", "Your Name"], check=True)

    # initial commit on main
    (workdir / "README.md").write_text("hello world\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(workdir), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(workdir), "commit", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(workdir), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(workdir), "push", "-u", "origin", "main"], check=True)

    return workdir


def test_slugify_repo_url_variants():
    assert core.slugify_repo_url("https://github.com/org/repo.git") == "org_repo"
    assert core.slugify_repo_url("git@github.com:Org/Repo") == "org_repo"
    assert core.slugify_repo_url("ssh://git@github.com/org/re.po") == "org_re_po"


def test_ensure_app_dirs_uses_home(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    repo_path, report_path = core.ensure_app_dirs("example_repo")

    assert repo_path == fake_home / core.APP_DIR_NAME / "repos" / "example_repo"
    assert report_path == fake_home / core.APP_DIR_NAME / "reports" / "example_repo"
    # The repo directory itself is created lazily by callers, but parents should exist.
    assert repo_path.parent.is_dir()
    assert report_path.is_dir()


def test_read_text_file_respects_limits(tmp_path):
    text_file = tmp_path / "sample.txt"
    text_file.write_text("sample", encoding="utf-8")
    assert core.read_text_file(text_file) == "sample"

    binary_file = tmp_path / "bin.dat"
    binary_file.write_bytes(b"\0binary")
    assert core.read_text_file(binary_file) is None

    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"a" * (core.MAX_FILE_SIZE_BYTES + 1))
    assert core.read_text_file(large_file) is None


def test_guess_and_slug_helpers():
    assert core.guess_language_from_path("script.py") == "python"
    assert core.guess_language_from_path("unknown.ext") == ""
    assert core.slugify_branch_name("feature/new#work") == "feature_new_work"


def test_build_tree_from_paths():
    tree = core.build_tree_from_paths(
        "repo",
        ["dir/file_b.txt", "dir/sub/file_a.txt", "alpha.txt"],
    )

    assert tree.splitlines()[0] == "repo"
    assert "alpha.txt" in tree
    assert "dir" in tree
    assert "file_a.txt" in tree


def test_get_remote_branch_names_parses_output(monkeypatch):
    sample_output = """
origin/HEAD
origin/main
origin/feature/test
upstream/ignored
    """

    monkeypatch.setattr(core, "run_git", lambda repo, args: sample_output)
    branches = core.get_remote_branch_names(Path("/tmp/repo"))

    assert branches == {"main", "feature/test"}


def test_compute_branch_diff_reports_missing_remote(git_repo):
    result = core.compute_branch_diff(git_repo, "missing", base_branch="main")

    assert not result.ok
    assert "origin/missing" in result.message


def test_compute_branch_diff_detects_changes(git_repo):
    # create feature branch with changes
    subprocess.run(["git", "-C", str(git_repo), "checkout", "-b", "feature"], check=True)
    (git_repo / "README.md").write_text("hello world\nmore text\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "commit", "-am", "update"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "push", "-u", "origin", "feature"], check=True)

    result = core.compute_branch_diff(git_repo, "feature", base_branch="main")

    assert result.ok
    assert result.has_changes
    assert "more text" in result.diff_text


def test_prompt_builders_include_content():
    branch_body = core.build_single_branch_prompt(
        "branch_comparison",
        "### FILE: file.txt\n``\ncontent\n``\n",
    )
    assert "BEGIN DOCUMENT" in branch_body

    combined = core.build_branch_comparison_prompt(
        spec_path="spec.md",
        spec_content="Goal",
        branch_markdown={"main": "main content"},
    )

    assert prompts.load_prompt("branch_comparison") in combined
    assert "spec.md" in combined
    assert "main content" in combined
