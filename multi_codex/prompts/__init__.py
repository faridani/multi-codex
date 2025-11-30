from __future__ import annotations

from importlib import resources
from typing import Dict

_PROMPT_FILES: Dict[str, str] = {
    "branch_comparison": "branch_comparison.md",
    "arch_deep_dive": "arch_deep_dive.md",
    "feature_security_analysis": "feature_security_analysis.md",
    "pr_long_context": "pr_long_context.md",
}


def load_prompt(name: str) -> str:
    """Load a prompt by logical name from the bundled markdown files."""
    filename = _PROMPT_FILES.get(name)
    if not filename:
        raise KeyError(f"Unknown prompt: {name}")

    with resources.files(__package__).joinpath(filename).open("r", encoding="utf-8") as f:
        return f.read().strip()
