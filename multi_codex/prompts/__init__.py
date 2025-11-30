from importlib import resources
from typing import Dict

_PROMPT_FILES: Dict[str, str] = {
    "branch_comparison": "branch_comparison.md",
    "arch_deep_dive": "arch_deep_dive.md",
    "feature_security_analysis": "feature_security_analysis.md",
    "pr_long_context": "pr_long_context.md",
}


def load_prompt(name: str) -> str:
    """Load a prompt markdown string by logical name.

    Parameters
    ----------
    name: str
        Logical prompt key (e.g., ``"pr_long_context"``).

    Returns
    -------
    str
        The prompt content as a string.

    Raises
    ------
    KeyError
        If the prompt name is unknown.
    FileNotFoundError
        If the mapped prompt file is missing.
    """

    filename = _PROMPT_FILES.get(name)
    if filename is None:
        raise KeyError(f"Unknown prompt name: {name}")

    with resources.files(__package__).joinpath(filename).open("r", encoding="utf-8") as f:
        return f.read()


__all__ = ["load_prompt"]
