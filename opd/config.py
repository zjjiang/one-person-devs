"""Configuration loading from opd.yaml with env var interpolation."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def _interpolate_env(value: str) -> str:
    """Replace ${ENV_VAR} patterns with environment variable values."""
    return re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        value,
    )


def _walk_interpolate(obj):
    """Recursively interpolate env vars in a config dict."""
    if isinstance(obj, str):
        return _interpolate_env(obj)
    if isinstance(obj, dict):
        return {k: _walk_interpolate(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_interpolate(v) for v in obj]
    return obj


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8765
    reload: bool = False


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///opd.db"


class WorkspaceConfig(BaseModel):
    base_dir: str = "./workspace"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    dir: str = "./logs"


class HealthCheckConfig(BaseModel):
    interval: int = 300
    timeout: int = 10


class CapabilityConfig(BaseModel):
    provider: str
    config: dict = Field(default_factory=dict)
    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    capabilities: dict[str, CapabilityConfig] = Field(default_factory=dict)


def load_config(path: str | Path = "opd.yaml") -> AppConfig:
    """Load config from YAML file with env var interpolation."""
    path = Path(path)
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        raw = _walk_interpolate(raw)
    else:
        raw = {}
    return AppConfig(**raw)
