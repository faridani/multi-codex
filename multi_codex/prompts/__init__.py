from __future__ import annotations

import importlib.resources as resources
from typing import Dict

PROMPT_FILES: Dict[str, str] = {
    "branch_comparison": "branch_comparison.md",
    "architecture_report": "architecture_report.md",
    "arch_deep_dive": "architecture_report.md",
    "feature_security_modernization": "feature_security_modernization.md",
    "feature_security_analysis": "feature_security_modernization.md",
    "pr_long_context": "pr_long_context.md",
}


def load_prompt(name: str) -> str:
    """Load a prompt markdown file by logical name."""

    if name not in PROMPT_FILES:
        raise KeyError(f"Unknown prompt '{name}'")

    filename = PROMPT_FILES[name]
    content = resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
    return content.strip()


__all__ = ["load_prompt", "PROMPT_FILES"]
