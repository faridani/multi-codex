import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import multi_codex.ui as ui


def test_copy_to_clipboard_uses_platform_commands(monkeypatch):
    captured = {}

    def fake_run(cmd, input=None, text=None, check=None):  # noqa: A002
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ui.shutil, "which", lambda name: True)
    monkeypatch.setattr(ui.subprocess, "run", fake_run)

    assert ui.copy_to_clipboard("hello")
    assert captured["cmd"] == ["pbcopy"]

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ui.shutil, "which", lambda name: name == "wl-copy")
    captured.clear()
    assert ui.copy_to_clipboard("hi")
    assert captured["cmd"] == ["wl-copy"]

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ui.shutil, "which", lambda name: True)
    captured.clear()
    assert ui.copy_to_clipboard("hi")
    assert captured["cmd"] == ["clip"]


def test_monitor_branches_adds_new_branch_and_starts(monkeypatch):
    responses = iter([True, True])  # add branch, then start analysis

    async def fake_sleep(_delay: float):  # noqa: ARG001
        return None

    def fake_ask_yes_no(*_args, **_kwargs):
        return next(responses)

    def fake_get_remote_branch_names(_repo_path):
        return {"feature/new"}

    monkeypatch.setattr(ui, "ask_yes_no", fake_ask_yes_no)
    monkeypatch.setattr(ui.core, "run_git", lambda *_args: None)
    monkeypatch.setattr(ui.core, "get_remote_branch_names", fake_get_remote_branch_names)
    monkeypatch.setattr(ui.asyncio, "sleep", fake_sleep)

    selected = asyncio.run(ui.monitor_branches(Path("/tmp/repo"), poll_interval=0))

    assert "feature/new" in selected
    assert selected["feature/new"].name == "feature/new"


def test_main_generates_architecture_report(monkeypatch, tmp_path):
    repo_url = "https://github.com/example/repo"
    runner = CliRunner()

    repo_dir = tmp_path / "repos" / "example_repo"
    report_dir = tmp_path / "reports" / "example_repo"

    def fake_ensure_app_dirs(_slug):
        repo_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        return repo_dir, report_dir

    monkeypatch.setattr(ui, "prompt_for_branch_selection", lambda *_args, **_kwargs: "feature")
    monkeypatch.setattr(ui, "ensure_local_clone", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui.core, "ensure_app_dirs", fake_ensure_app_dirs)
    monkeypatch.setattr(ui.core, "slugify_repo_url", lambda *_args, **_kwargs: "example_repo")
    monkeypatch.setattr(ui.core, "build_architecture_report", lambda *_args, **_kwargs: "ARCH")
    monkeypatch.setattr(ui, "copy_to_clipboard", lambda *_args, **_kwargs: False)

    result = runner.invoke(
        ui.app,
        [
            "--repo-url",
            repo_url,
            "--workflow",
            "architecture",
        ],
    )

    assert result.exit_code == 0

    output_path = report_dir / "architecture_report_feature.md"
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == "ARCH"
