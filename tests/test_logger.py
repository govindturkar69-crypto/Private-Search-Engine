import logging
from pathlib import Path
import pytest
from src.logger import setup_logging


@pytest.mark.unit
def test_setup_logging_creates_directory_and_file(tmp_path: Path):
    """Verify setup_logging creates the directory and logs output to file."""
    log_dir = tmp_path / "custom_logs" / "nested"
    log_file = log_dir / "test.log"

    assert not log_dir.exists()

    logger = setup_logging(log_level="DEBUG", log_file=str(log_file))

    assert log_dir.exists()
    assert isinstance(logger, logging.Logger)
    assert logger.level == logging.DEBUG

    test_message = "Test logging entry verification"
    logger.info(test_message)

    # Flush handlers to ensure file write
    for handler in logger.handlers:
        handler.flush()

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert test_message in content


@pytest.mark.unit
def test_setup_logging_idempotent_handlers(tmp_path: Path):
    """Verify setup_logging does not duplicate handlers when invoked repeatedly."""
    log_file = tmp_path / "idempotent.log"
    logger1 = setup_logging("INFO", str(log_file))
    handler_count_1 = len(logger1.handlers)

    logger2 = setup_logging("INFO", str(log_file))
    handler_count_2 = len(logger2.handlers)

    assert handler_count_1 == handler_count_2
