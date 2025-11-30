"""Prompt loading utilities for multi_codex."""
from importlib import resources
from typing import Dict

_PROMPT_FILES: Dict[str, str] = {
    "branch_comparison": "branch_comparison.md",
    "arch_deep_dive": "arch_deep_dive.md",
    "feature_security_analysis": "feature_security_analysis.md",
    "pr_long_context": "pr_long_context.md",
}


def load_prompt(name: str) -> str:
    """Load the prompt markdown by logical name."""
    filename = _PROMPT_FILES.get(name)
    if not filename:
        raise KeyError(f"Unknown prompt name: {name}")

    with resources.files(__package__).joinpath(filename).open("r", encoding="utf-8") as file:
        return file.read()
