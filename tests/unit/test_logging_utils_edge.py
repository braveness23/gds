
import pytest
from src.core.logging_utils import setup_logging
import logging

def test_invalid_log_level():
    with pytest.raises(ValueError):
        setup_logging(level='notalevel')

def test_logging_to_file_permission_error(tmp_path, monkeypatch):
    log_file = tmp_path / "log.txt"
    log_file.write_text("")
    log_file.chmod(0)
    try:
        with pytest.raises(PermissionError):
            logging.basicConfig(filename=str(log_file))
            logging.getLogger().info("test")
    finally:
        log_file.chmod(0o644)
