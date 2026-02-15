"""Tests for configuration loading."""

import os
import tempfile

from opd.config import load_config, _interpolate_env


class TestConfig:
    def test_default_config(self):
        config = load_config("nonexistent.yaml")
        assert config.server.port == 8765
        assert config.database.url == "sqlite+aiosqlite:///opd.db"

    def test_env_interpolation(self):
        os.environ["TEST_OPD_VAR"] = "hello"
        try:
            assert _interpolate_env("${TEST_OPD_VAR}") == "hello"
            assert _interpolate_env("prefix_${TEST_OPD_VAR}_suffix") == "prefix_hello_suffix"
        finally:
            del os.environ["TEST_OPD_VAR"]

    def test_missing_env_var_kept(self):
        result = _interpolate_env("${NONEXISTENT_OPD_VAR_12345}")
        assert result == "${NONEXISTENT_OPD_VAR_12345}"

    def test_load_yaml_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("server:\n  port: 9999\n  host: '127.0.0.1'\n")
            f.flush()
            config = load_config(f.name)
        assert config.server.port == 9999
        assert config.server.host == "127.0.0.1"
        os.unlink(f.name)
