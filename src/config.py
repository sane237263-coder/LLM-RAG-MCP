# ============================================================
# src/config.py - 配置管理
# ============================================================
"""加载 YAML 配置并提供类型化访问。"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class EmbeddingConfig:
    api_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "BAAI/bge-m3"
    data_url: str = ""
    top_k: int = 3


@dataclass
class SystemConfig:
    max_tool_rounds: int = 10
    log_level: str = "INFO"
    memory_file: str = "chat_memory.json"


@dataclass
class AppConfig:
    llm: LLMConfig
    mcp_servers: list[MCPServerConfig]
    embedding: EmbeddingConfig
    system: SystemConfig


def _load_dotenv(dotenv_path: Path | None = None) -> None:
    """加载 .env 文件到环境变量（手动解析，零依赖）。

    格式: KEY=value 或 KEY="value"，支持 # 注释。
    """
    if dotenv_path is None:
        dotenv_path = Path(".env")
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """从 YAML 文件加载配置，API Key 优先从环境变量读取。"""
    # 先加载 .env 到环境变量
    _load_dotenv()

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    llm_raw = raw.get("llm", {})
    llm_raw["api_key"] = os.getenv("DEEPSEEK_API_KEY", llm_raw.get("api_key", ""))
    llm = LLMConfig(**llm_raw)

    servers = []
    for s in raw.get("mcp_servers", []):
        servers.append(MCPServerConfig(
            name=s["name"],
            command=s["command"],
            args=s.get("args", []),
            env=s.get("env", {}),
        ))

    emb_raw = raw.get("embedding", {})
    emb_raw["api_key"] = os.getenv("SILICONFLOW_API_KEY", emb_raw.get("api_key", ""))
    embedding = EmbeddingConfig(**emb_raw)

    system = SystemConfig(**raw.get("system", {}))

    return AppConfig(llm=llm, mcp_servers=servers, embedding=embedding, system=system)