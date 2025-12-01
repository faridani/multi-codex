import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys

import multi_codex.ui as ui


def test_monitor_branches_adds_new_branch_and_starts(monkeypatch):
    responses = iter([True, True])  # add branch, then start analysis

    def fake_ask_yes_no(*_args, **_kwargs):
        return next(responses)

    def fake_get_remote_branch_names(_repo_path):
        return {"feature/new"}

    async def fake_to_thread(func, *args, **kwargs):
        func(*args, **kwargs)

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(ui, "ask_yes_no", fake_ask_yes_no)
    monkeypatch.setattr(ui.core, "run_git", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui.core, "get_remote_branch_names", fake_get_remote_branch_names)
    monkeypatch.setattr(ui.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(ui.asyncio, "sleep", fake_sleep)

    selected = asyncio.run(ui.monitor_branches(Path("/tmp/repo")))

    assert "feature/new" in selected
    assert selected["feature/new"].name == "feature/new"


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


def test_main_invokes_launch_interactive(monkeypatch):
    called = {}
    monkeypatch.setattr(ui, "launch_interactive", lambda: called.setdefault("ran", True))

    ui.main()

    assert called.get("ran") is True
