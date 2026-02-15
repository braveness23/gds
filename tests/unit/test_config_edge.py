import pytest
from src.config.config import Config
import os

def test_load_corrupt_config(tmp_path):
    corrupt_file = tmp_path / "corrupt.yaml"
    corrupt_file.write_text(": bad yaml : : :")
    with pytest.raises(Exception):
        Config.load(str(corrupt_file))

def test_missing_fields():
    config = Config()
    assert config.get('nonexistent.field', 'default') == 'default'

def test_invalid_types(tmp_path):
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("system:\n  node_id: [1,2,3]")
    config = Config.load(str(bad_file))
    assert isinstance(config.get('system.node_id'), list)

def test_permission_error(tmp_path, monkeypatch):
    file_path = tmp_path / "protected.yaml"
    file_path.write_text("system: {}")
    os.chmod(file_path, 0)
    try:
        with pytest.raises(Exception):
            Config.load(str(file_path))
    finally:
        os.chmod(file_path, 0o644)
