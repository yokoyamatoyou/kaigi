import json
import os
from core.config_manager import ConfigManager


def test_config_loading(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "envkey")
    monkeypatch.setenv("API_CALL_DELAY_SECONDS", "0.5")
    config_data = {
        "default_temperature": 0.3,
        "window_title": "Test App"
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data, ensure_ascii=False), encoding="utf-8")
    manager = ConfigManager(config_file_path=str(config_file))
    config = manager.config
    assert config.openai_api_key == "envkey"
    assert config.default_temperature == 0.3
    assert config.window_title == "Test App"
    assert config.api_call_delay_seconds == 0.5

