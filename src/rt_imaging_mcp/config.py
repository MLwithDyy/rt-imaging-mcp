"""Server configuration.

There is no default root directory (rule R3): the server refuses to start
without one. Limits are conservative by default (rule R8).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from rt_imaging_mcp.security.allowlist import OPT_IN_KEYWORDS
from rt_imaging_mcp.security.errors import ConfigError
from rt_imaging_mcp.security.roi_names import MAX_NAME_LENGTH, normalize

ENV_ROOT = "RT_IMAGING_MCP_ROOT"


@dataclass(frozen=True)
class Config:
    root: Path
    max_files: int = 5_000
    max_depth: int = 8
    max_file_bytes: int = 1024**3
    enabled_opt_in_tags: frozenset[str] = field(default_factory=frozenset)
    extra_roi_names: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.max_files < 1 or self.max_depth < 0 or self.max_file_bytes < 1:
            raise ConfigError()
        if not self.enabled_opt_in_tags <= OPT_IN_KEYWORDS:
            raise ConfigError()
        for name in self.extra_roi_names:
            normalized = normalize(name)
            if not normalized or len(normalized) > MAX_NAME_LENGTH:
                raise ConfigError()

    @classmethod
    def from_root(cls, root: str | Path, **overrides: object) -> Config:
        try:
            resolved = Path(root).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            raise ConfigError() from None
        if not resolved.is_dir():
            raise ConfigError()
        return cls(root=resolved, **overrides)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls) -> Config:
        value = os.environ.get(ENV_ROOT)
        if not value:
            raise ConfigError()
        return cls.from_root(value)
