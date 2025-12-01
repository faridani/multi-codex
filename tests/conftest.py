import sys
from pathlib import Path
import types

# Ensure the repository root is on sys.path so tests can import multi_codex
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyEncoding:
    def encode(self, text: str, disallowed_special=None):  # pragma: no cover - trivial stub
        return list(text.encode())


def _encoding_for_model(_model: str):  # pragma: no cover - trivial stub
    return _DummyEncoding()


def _get_encoding(_name: str):  # pragma: no cover - trivial stub
    return _DummyEncoding()


tiktoken_stub = types.SimpleNamespace(
    encoding_for_model=_encoding_for_model, get_encoding=_get_encoding
)

sys.modules.setdefault("tiktoken", tiktoken_stub)
