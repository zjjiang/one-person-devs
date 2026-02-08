from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class DatabaseConfig(BaseModel):
    url: str = "mysql+aiomysql://root:@localhost:3306/one_person_devs"


class WorkspaceConfig(BaseModel):
    base_dir: str = "./workspace"


class ProviderConfig(BaseModel):
    type: str = ""
    config: dict[str, Any] = {}


class ProvidersConfig(BaseModel):
    requirement: ProviderConfig = ProviderConfig()
    document: ProviderConfig = ProviderConfig()
    scm: ProviderConfig = ProviderConfig()
    sandbox: ProviderConfig = ProviderConfig()
    ci: ProviderConfig = ProviderConfig()
    ai: ProviderConfig = ProviderConfig()
    notification: ProviderConfig = ProviderConfig()


class OPDConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    providers: ProvidersConfig = ProvidersConfig()

    @classmethod
    def load(cls, path: str | Path | None = None) -> OPDConfig:
        if path is None:
            path = Path(os.getcwd()) / "opd.yaml"
        else:
            path = Path(path)

        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if raw is None:
            return cls()

        return cls.model_validate(raw)
