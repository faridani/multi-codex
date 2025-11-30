from types import SimpleNamespace
import sys

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
