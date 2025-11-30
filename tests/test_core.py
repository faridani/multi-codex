from types import SimpleNamespace

import multi_codex.core as core


def test_slugify_repo_url_handles_common_variants():
    assert core.slugify_repo_url("https://github.com/user/repo.git") == "user_repo"
    assert core.slugify_repo_url("git@github.com:user/repo.git") == "user_repo"
    assert core.slugify_repo_url("ssh://git@github.com/user/repo") == "user_repo"
    assert core.slugify_repo_url("invalid") == "invalid"


def test_ensure_app_dirs_creates_structure(monkeypatch, tmp_path):
    monkeypatch.setattr(core.Path, "home", lambda: tmp_path)

    repo_path, report_path = core.ensure_app_dirs("example_repo")

    assert repo_path.parent.exists()
    assert report_path.exists()
    assert repo_path.parent.name == "repos"
    assert report_path.parent.name == "reports"


def test_read_text_file_skips_large_and_binary_files(tmp_path):
    text_file = tmp_path / "file.txt"
    text_file.write_text("hello", encoding="utf-8")

    binary_file = tmp_path / "bin.dat"
    binary_file.write_bytes(b"\x00\x01binary")

    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"a" * (core.MAX_FILE_SIZE_BYTES + 1))

    assert core.read_text_file(text_file) == "hello"
    assert core.read_text_file(binary_file) is None
    assert core.read_text_file(large_file) is None


def test_build_tree_from_paths_renders_sorted_tree():
    tree = core.build_tree_from_paths(
        "repo",
        [
            "src/app.py",
            "src/utils/helpers.py",
            "README.md",
            "docs/intro.md",
        ],
    )

    expected = """repo
├── docs
│   └── intro.md
├── src
│   ├── utils
│   │   └── helpers.py
│   └── app.py
└── README.md"""
    assert tree == expected


def test_slugify_branch_name_replaces_special_characters():
    assert core.slugify_branch_name("feature/add stuff#1") == "feature_add_stuff_1"


def test_collect_branch_markdown_reads_supported_files(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "sync_remote_branch", lambda repo_path, branch_name: None)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "node_modules").mkdir()

    (repo / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (repo / "README.md").write_text("# Title\nBody", encoding="utf-8")
    (repo / "node_modules" / "ignore.js").write_text("console.log('ignore')", encoding="utf-8")

    result = core.collect_branch_markdown(repo, "feature")

    assert "Project: repo (Branch: feature)" in result
    assert "### FILE: README.md" in result
    assert "### FILE: src/main.py" in result
    assert "node_modules" not in result


def test_build_branch_comparison_prompt(monkeypatch):
    monkeypatch.setattr(core.prompts, "load_prompt", lambda name: f"system:{name}")

    branch_markdown = {"a": "branch a", "b": "branch b"}
    combined = core.build_branch_comparison_prompt("spec.md", "Spec content", branch_markdown)

    assert "system:branch_comparison" in combined
    assert "Spec content" in combined
    assert "# a branch content" in combined or "branch a" in combined
    assert "branch b" in combined


def test_compute_branch_diff_handles_missing_refs(monkeypatch, tmp_path):
    existing_refs = {"refs/remotes/origin/main"}

    def fake_subprocess_run(cmd, check=False, stdout=None, stderr=None, text=None):
        ref = cmd[-1]
        return SimpleNamespace(returncode=0 if ref in existing_refs else 1, stdout="", stderr="")

    monkeypatch.setattr(core, "subprocess", SimpleNamespace(run=fake_subprocess_run, PIPE=None))
    monkeypatch.setattr(core, "run_git", lambda repo, args: "")

    result = core.compute_branch_diff(tmp_path, "feature")

    assert not result.ok
    assert "origin/feature" in result.message


def test_compute_branch_diff_with_and_without_changes(monkeypatch, tmp_path):
    existing_refs = {"refs/remotes/origin/main", "refs/remotes/origin/feature"}

    def fake_subprocess_run(cmd, check=False, stdout=None, stderr=None, text=None):
        ref = cmd[-1]
        return SimpleNamespace(returncode=0 if ref in existing_refs else 1, stdout="", stderr="")

    def fake_run_git(repo, args):
        if args[0] == "fetch":
            return ""
        if args[0] == "diff":
            return "DIFF" if "..." in args[1] else ""
        raise AssertionError(f"Unexpected git args: {args}")

    monkeypatch.setattr(core, "subprocess", SimpleNamespace(run=fake_subprocess_run, PIPE=None))
    monkeypatch.setattr(core, "run_git", fake_run_git)

    diff_with_changes = core.compute_branch_diff(tmp_path, "feature")
    assert diff_with_changes.ok
    assert diff_with_changes.has_changes
    assert diff_with_changes.diff_text == "DIFF"

    def fake_run_git_no_changes(repo, args):
        if args[0] == "fetch":
            return ""
        if args[0] == "diff":
            return ""
        raise AssertionError(f"Unexpected git args: {args}")

    monkeypatch.setattr(core, "run_git", fake_run_git_no_changes)
    diff_without_changes = core.compute_branch_diff(tmp_path, "feature")
    assert diff_without_changes.ok
    assert not diff_without_changes.has_changes


def test_build_pr_mega_prompt_uses_branch_and_diff(monkeypatch):
    monkeypatch.setattr(core.prompts, "load_prompt", lambda name: "SYSTEM")
    monkeypatch.setattr(core, "collect_branch_markdown", lambda repo, branch: "BRANCH MD")
    monkeypatch.setattr(
        core,
        "compute_branch_diff",
        lambda repo, branch, base: core.DiffResult(True, True, "", "DIFF"),
    )

    prompt = core.build_pr_mega_prompt("/tmp/repo", "feature", "main")

    assert "BRANCH MD" in prompt
    assert "DIFF" in prompt
    assert "SYSTEM" in prompt


def test_build_reports_use_correct_prompts(monkeypatch):
    monkeypatch.setattr(core, "collect_branch_markdown", lambda repo, branch: "BRANCH")
    monkeypatch.setattr(core.prompts, "load_prompt", lambda name: f"PROMPT:{name}")

    arch = core.build_architecture_report("/tmp/repo", "main")
    feature = core.build_feature_security_report("/tmp/repo", "main")

    assert "PROMPT:architecture_report" in arch
    assert "PROMPT:feature_security_modernization" in feature
