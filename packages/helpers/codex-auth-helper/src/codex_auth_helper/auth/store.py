from __future__ import annotations as _annotations

import contextlib
import json
import os
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from uuid import uuid4

from .state import CodexAuthState

__all__ = ("CodexAuthStore",)


@dataclass(slots=True)
class CodexAuthStore:
    path: Path

    def read_state(self) -> CodexAuthState:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Codex auth file was not found at `{self.path}`.") from exc

        try:
            raw = json.loads(text)
        except JSONDecodeError as exc:
            raise ValueError(
                f"Codex auth file at `{self.path}` does not contain valid JSON."
            ) from exc

        if not isinstance(raw, dict):
            raise ValueError(f"Codex auth file at `{self.path}` must contain a JSON object.")
        return CodexAuthState.from_json_dict(raw)

    def write_state(self, state: CodexAuthState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(state.to_json_dict(), indent=2) + "\n"
        temp_path = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            file_descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as temp_file:
                temp_file.write(encoded)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, self.path)
            with contextlib.suppress(OSError):
                os.chmod(self.path, 0o600)
            _fsync_directory(self.path.parent)
        finally:
            temp_path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    try:
        directory_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
