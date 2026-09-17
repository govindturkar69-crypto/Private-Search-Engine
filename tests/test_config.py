from pathlib import Path
import pytest
import yaml
from src.config import Config, load_config


@pytest.mark.unit
def test_default_config():
    """Verify default configuration values without config file or env vars."""
    cfg = load_config(config_path="non_existent_file.yaml", env={})
    assert isinstance(cfg, Config)
    assert cfg.crawl.crawl_delay == 1.0
    assert cfg.crawl.max_document_size == 10_485_760
    assert cfg.crawl.timeout == 10
    assert cfg.crawl.max_depth == 2
    assert cfg.crawl.user_agent == "PrivateSearchCrawler/1.0"
    assert cfg.index.database_path == "data/index.db"
    assert cfg.index.bm25_k1 == 1.5
    assert cfg.index.bm25_b == 0.75
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.port == 8000


@pytest.mark.unit
def test_yaml_config_loading(tmp_path: Path):
    """Verify configuration loads properly from a YAML file."""
    custom_yaml = tmp_path / "custom_config.yaml"
    data = {
        "crawl": {
            "crawl_delay": 2.5,
            "timeout": 15,
            "max_depth": 3,
            "user_agent": "CustomAgent/2.0",
        },
        "index": {
            "database_path": "data/custom.db",
            "bm25_k1": 1.2,
            "bm25_b": 0.8,
        },
        "server": {
            "host": "127.0.0.1",
            "port": 9000,
        },
    }
    with open(custom_yaml, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    cfg = load_config(config_path=str(custom_yaml), env={})
    assert cfg.crawl.crawl_delay == 2.5
    assert cfg.crawl.timeout == 15
    assert cfg.crawl.max_depth == 3
    assert cfg.crawl.user_agent == "CustomAgent/2.0"
    assert cfg.index.database_path == "data/custom.db"
    assert cfg.index.bm25_k1 == 1.2
    assert cfg.index.bm25_b == 0.8
    assert cfg.server.host == "127.0.0.1"
    assert cfg.server.port == 9000


@pytest.mark.unit
def test_env_var_precedence_over_yaml(tmp_path: Path):
    """Verify Environment Variables take precedence over config.yaml and defaults."""
    custom_yaml = tmp_path / "custom_config.yaml"
    data = {
        "crawl": {
            "crawl_delay": 2.0,
            "max_depth": 4,
        },
        "index": {
            "database_path": "data/from_yaml.db",
        },
        "server": {
            "port": 8080,
        },
    }
    with open(custom_yaml, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    env_overrides = {
        "CRAWL_DELAY": "5.0",
        "DATABASE_PATH": "data/from_env.db",
        "SERVER_PORT": "9999",
        "TIMEOUT": "25",
    }

    cfg = load_config(config_path=str(custom_yaml), env=env_overrides)
    # CRAWL_DELAY should come from env (5.0), not YAML (2.0)
    assert cfg.crawl.crawl_delay == 5.0
    # max_depth was in YAML (4) and not in env, so YAML value is used
    assert cfg.crawl.max_depth == 4
    # TIMEOUT was not in YAML, so env value (25) overrides default (10)
    assert cfg.crawl.timeout == 25
    # DATABASE_PATH should come from env
    assert cfg.index.database_path == "data/from_env.db"
    # SERVER_PORT should come from env
    assert cfg.server.port == 9999
