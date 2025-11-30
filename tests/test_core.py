import subprocess

import pytest

from multi_codex import core


@pytest.fixture()
def temp_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(core.Path, "home", lambda: home)
    return home


def test_slugify_repo_url_handles_variations():
    assert core.slugify_repo_url("git@github.com:Owner/Repo.git") == "owner_repo"
    assert core.slugify_repo_url("https://github.com/Owner/Repo") == "owner_repo"
    assert core.slugify_repo_url("/custom/path") == "custom_path"


def test_ensure_app_dirs_creates_expected_paths(temp_home):
    repo_path, report_path = core.ensure_app_dirs("example_repo")

    assert repo_path == temp_home / core.APP_DIR_NAME / "repos" / "example_repo"
    assert report_path == temp_home / core.APP_DIR_NAME / "reports" / "example_repo"
    assert repo_path.parent.is_dir()
    assert report_path.is_dir()


def test_read_text_file_handles_binary_and_large(tmp_path, monkeypatch):
    text_file = tmp_path / "sample.txt"
    text_file.write_text("hello")
    assert core.read_text_file(text_file) == "hello"

    binary_file = tmp_path / "binary.bin"
    binary_file.write_bytes(b"\0\x01\x02")
    assert core.read_text_file(binary_file) is None

    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"a" * (core.MAX_FILE_SIZE_BYTES + 1))
    assert core.read_text_file(large_file) is None


@pytest.fixture()
def git_repo(tmp_path):
    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True)
    subprocess.run(
        ["git", "-C", str(origin), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
    )

    clone = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.email", "tester@example.com"], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.name", "Tester"], check=True)

    subprocess.run(["git", "-C", str(clone), "checkout", "-b", "main"], check=True)
    (clone / "file.txt").write_text("initial\n")
    subprocess.run(["git", "-C", str(clone), "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", str(clone), "commit", "-m", "Initial"], check=True)
    subprocess.run(["git", "-C", str(clone), "push", "-u", "origin", "main"], check=True)

    subprocess.run(["git", "-C", str(clone), "checkout", "-b", "feature"], check=True)
    (clone / "file.txt").write_text("initial\nfeature change\n")
    subprocess.run(["git", "-C", str(clone), "commit", "-am", "Feature"], check=True)
    subprocess.run(["git", "-C", str(clone), "push", "-u", "origin", "feature"], check=True)

    return clone


def test_get_remote_branch_names_discovers_origin_branches(git_repo):
    branches = core.get_remote_branch_names(git_repo)
    assert branches == {"feature", "main"}


def test_sync_remote_branch_checks_out_requested_branch(git_repo):
    core.sync_remote_branch(git_repo, "main")
    head = core.run_git(git_repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    assert head == "main"


def test_collect_branch_markdown_includes_tree_and_content(git_repo):
    markdown = core.collect_branch_markdown(git_repo, "feature")

    assert "Project Structure" in markdown
    assert "file.txt" in markdown
    assert "feature change" in markdown


def test_build_tree_from_paths_orders_files():
    tree = core.build_tree_from_paths(
        "project",
        ["src/main.py", "README.md", "docs/index.md"],
    )
    expected = """
project
├── docs
│   └── index.md
├── src
│   └── main.py
└── README.md
""".strip()

    assert tree == expected


def test_slugify_branch_name_replaces_problematic_characters():
    assert core.slugify_branch_name("feature/new#1") == "feature_new_1"


def test_compute_branch_diff_detects_changes(git_repo):
    diff = core.compute_branch_diff(git_repo, "feature", base_branch="main")
    assert diff.ok is True
    assert diff.has_changes is True
    assert "feature change" in diff.diff_text


def test_compute_branch_diff_handles_missing_branch(git_repo):
    diff = core.compute_branch_diff(git_repo, "missing", base_branch="main")
    assert diff.ok is False
    assert diff.has_changes is False
    assert "origin/missing" in diff.message
