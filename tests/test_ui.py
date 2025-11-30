from __future__ import annotations

import subprocess
from typing import Iterator

from multi_codex import ui


def _input_sequence(values: list[str]) -> Iterator[str]:
    for value in values:
        yield value


def test_choose_from_list_validates_and_returns_choice(monkeypatch, capsys):
    inputs = _input_sequence(["abc", "5", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    result = ui.choose_from_list(["first", "second", "third"], "Pick one")

    assert result == "second"
    output = capsys.readouterr().out
    assert "Please enter a valid number" in output
    assert "Choice out of range" in output


def test_select_branch_accepts_number_and_name(monkeypatch):
    branches = ["main", "feature", "bugfix"]

    number_inputs = _input_sequence(["2"])
    monkeypatch.setattr("builtins.input", lambda _: next(number_inputs))
    assert ui.select_branch(branches, "Select") == "feature"

    name_inputs = _input_sequence(["bugfix"])
    monkeypatch.setattr("builtins.input", lambda _: next(name_inputs))
    assert ui.select_branch(branches, "Select") == "bugfix"


def test_select_branch_handles_invalid_and_cancel(monkeypatch, capsys):
    branches = ["main", "feature"]
    inputs = _input_sequence(["invalid", "", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    assert ui.select_branch(branches, "Select") is None
    output = capsys.readouterr().out
    assert "Branch not recognized" in output


def test_copy_to_clipboard_mac_success(monkeypatch):
    monkeypatch.setattr(ui.sys, "platform", "darwin")
    monkeypatch.setattr(
        ui.shutil, "which", lambda cmd: "/usr/bin/pbcopy" if cmd == "pbcopy" else None
    )

    called: dict[str, object] = {}

    def fake_run(cmd, input=None, text=None, check=None):  # noqa: ANN001
        called["cmd"] = cmd
        called["input"] = input
        called["text"] = text
        called["check"] = check

    monkeypatch.setattr(ui.subprocess, "run", fake_run)

    assert ui.copy_to_clipboard("payload") is True
    assert called["cmd"] == ["pbcopy"]
    assert called["input"] == "payload"
    assert called["text"] is True
    assert called["check"] is True


def test_copy_to_clipboard_linux_prefers_wayland(monkeypatch):
    monkeypatch.setattr(ui.sys, "platform", "linux")
    monkeypatch.setattr(
        ui.shutil, "which", lambda cmd: "/usr/bin/wl-copy" if cmd == "wl-copy" else None
    )

    called: dict[str, object] = {}
    monkeypatch.setattr(ui.subprocess, "run", lambda cmd, **_: called.setdefault("cmd", cmd))

    assert ui.copy_to_clipboard("data") is True
    assert called["cmd"] == ["wl-copy"]


def test_copy_to_clipboard_linux_falls_back_to_xclip(monkeypatch):
    monkeypatch.setattr(ui.sys, "platform", "linux")

    def fake_which(cmd: str) -> str | None:
        if cmd == "xclip":
            return "/usr/bin/xclip"
        return None

    monkeypatch.setattr(ui.shutil, "which", fake_which)

    captured: dict[str, object] = {}

    def fake_run(cmd, input=None, text=None, check=None):  # noqa: ANN001
        if cmd[0] == "xclip":
            captured["cmd"] = cmd
            captured["input"] = input
            captured["text"] = text
            captured["check"] = check
        else:
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(ui.subprocess, "run", fake_run)

    assert ui.copy_to_clipboard("backup") is True
    assert captured["cmd"] == ["xclip", "-selection", "clipboard"]
    assert captured["input"] == "backup"
    assert captured["text"] is True
    assert captured["check"] is True


def test_copy_to_clipboard_missing_tool(monkeypatch):
    monkeypatch.setattr(ui.sys, "platform", "linux")
    monkeypatch.setattr(ui.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(
        ui.subprocess, "run", lambda *_, **__: (_ for _ in ()).throw(AssertionError())
    )

    assert ui.copy_to_clipboard("irrelevant") is False
