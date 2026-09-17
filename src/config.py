import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
import yaml


@dataclass
class CrawlConfig:
    crawl_delay: float = 1.0
    max_document_size: int = 10_485_760  # 10MB
    timeout: int = 10
    max_depth: int = 2
    user_agent: str = "PrivateSearchCrawler/1.0"

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class IndexConfig:
    database_path: str = "data/index.db"
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    rate_limit_per_minute: int = 100
    trusted_proxies: list[str] = field(default_factory=list)
    enable_hsts: bool = False
    max_offset: int = 1000
    log_queries: bool = True
    admin_token: Optional[str] = None

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class Config:
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _get_val(env_dict: Mapping[str, str], *keys: str) -> Optional[str]:
    for key in keys:
        if key in env_dict:
            return env_dict[key]
    return None


def normalize_environment(env_vars: Mapping[str, str]) -> str:
    """Resolve environment name with deterministic precedence.

    If either ENVIRONMENT or ENV specifies production, production is enforced
    to prevent accidental downgrade to less secure modes.
    Returns normalized string: 'production', 'test', or 'development'.
    """
    raw_environment = env_vars.get("ENVIRONMENT", "").strip().lower()
    raw_env = env_vars.get("ENV", "").strip().lower()

    if raw_environment in ("production", "prod") or raw_env in (
        "production",
        "prod",
    ):
        return "production"
    if raw_environment in ("test", "testing") or raw_env in ("test", "testing"):
        return "test"
    if raw_environment in ("development", "dev") or raw_env in (
        "development",
        "dev",
    ):
        return "development"

    return "development"


def load_config(
    config_path: str = "config.yaml",
    env: Optional[Mapping[str, str]] = None,
) -> Config:
    """Load configuration with precedence:
    Environment Variables > config.yaml > dataclass defaults.
    """
    env_vars: Mapping[str, str] = os.environ if env is None else env

    yaml_data: Dict[str, Any] = {}
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                yaml_data = loaded

    crawl_yaml = yaml_data.get("crawl", {}) or {}
    index_yaml = yaml_data.get("index", {}) or {}
    server_yaml = yaml_data.get("server", {}) or {}

    # Crawl Config overrides
    crawl_delay_val = _get_val(env_vars, "CRAWL_DELAY")
    max_doc_size_val = _get_val(env_vars, "MAX_DOCUMENT_SIZE")
    timeout_val = _get_val(env_vars, "TIMEOUT")
    max_depth_val = _get_val(env_vars, "MAX_DEPTH")
    user_agent_val = _get_val(env_vars, "USER_AGENT")

    crawl_kwargs: Dict[str, Any] = dict(crawl_yaml)
    if crawl_delay_val is not None:
        crawl_kwargs["crawl_delay"] = float(crawl_delay_val)
    if max_doc_size_val is not None:
        crawl_kwargs["max_document_size"] = int(max_doc_size_val)
    if timeout_val is not None:
        crawl_kwargs["timeout"] = int(timeout_val)
    if max_depth_val is not None:
        crawl_kwargs["max_depth"] = int(max_depth_val)
    if user_agent_val is not None:
        crawl_kwargs["user_agent"] = str(user_agent_val)

    # Index Config overrides
    db_path_val = _get_val(env_vars, "DATABASE_PATH", "DATABASE_URL")
    bm25_k1_val = _get_val(env_vars, "BM25_K1")
    bm25_b_val = _get_val(env_vars, "BM25_B")

    index_kwargs: Dict[str, Any] = dict(index_yaml)
    if db_path_val is not None:
        index_kwargs["database_path"] = str(db_path_val)
    if bm25_k1_val is not None:
        index_kwargs["bm25_k1"] = float(bm25_k1_val)
    if bm25_b_val is not None:
        index_kwargs["bm25_b"] = float(bm25_b_val)

    # Server Config overrides
    server_host_val = _get_val(env_vars, "SERVER_HOST", "HOST")
    server_port_val = _get_val(env_vars, "SERVER_PORT", "PORT")
    log_level_val = _get_val(env_vars, "LOG_LEVEL")
    rate_limit_val = _get_val(env_vars, "RATE_LIMIT_PER_MINUTE")
    enable_hsts_val = _get_val(env_vars, "ENABLE_HSTS")
    max_offset_val = _get_val(env_vars, "MAX_OFFSET")

    server_kwargs: Dict[str, Any] = dict(server_yaml)
    if server_host_val is not None:
        server_kwargs["host"] = str(server_host_val)
    if server_port_val is not None:
        server_kwargs["port"] = int(server_port_val)
    if log_level_val is not None:
        server_kwargs["log_level"] = str(log_level_val)
    if rate_limit_val is not None:
        server_kwargs["rate_limit_per_minute"] = int(rate_limit_val)
    if enable_hsts_val is not None:
        server_kwargs["enable_hsts"] = enable_hsts_val.lower() in ("true", "1", "yes")
    if max_offset_val is not None:
        server_kwargs["max_offset"] = int(max_offset_val)
    admin_token_val = _get_val(env_vars, "ADMIN_TOKEN")
    if admin_token_val is not None:
        server_kwargs["admin_token"] = str(admin_token_val)
    cors_origins_val = _get_val(env_vars, "CORS_ORIGINS")
    if cors_origins_val is not None:
        server_kwargs["cors_origins"] = [
            o.strip() for o in str(cors_origins_val).split(",") if o.strip()
        ]
    server_kwargs["environment"] = normalize_environment(env_vars)

    return Config(
        crawl=CrawlConfig(**crawl_kwargs),
        index=IndexConfig(**index_kwargs),
        server=ServerConfig(**server_kwargs),
    )
