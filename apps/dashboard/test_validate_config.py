from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_module_path = Path(__file__).resolve().parent / "validate-config.py"
_spec = importlib.util.spec_from_file_location("dashboard_validate_config", _module_path)
assert _spec is not None and _spec.loader is not None
config_validator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_validator)


class ValidateConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        example = Path(__file__).with_name("config.example.json")
        self.config = json.loads(example.read_text(encoding="utf-8"))

    def test_example_config_is_valid(self) -> None:
        config_validator.validate_config(self.config)

    def test_empty_stop_list_is_valid(self) -> None:
        self.config["bus"]["stops"] = []
        config_validator.validate_config(self.config)

    def test_unknown_keys_are_allowed(self) -> None:
        self.config["future_block"] = {"enabled": True}
        config_validator.validate_config(self.config)

    def test_non_object_root_is_rejected(self) -> None:
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config([])

    def test_missing_bus_stops_is_rejected(self) -> None:
        del self.config["bus"]["stops"]
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config(self.config)

    def test_missing_flights_location_is_rejected(self) -> None:
        del self.config["flights"]["location"]
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config(self.config)

    def test_missing_weather_location_is_rejected(self) -> None:
        del self.config["weather"]["location"]
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config(self.config)

    def test_invalid_stop_id_is_rejected(self) -> None:
        self.config["bus"]["stops"] = [{"id": "", "name": "Stop"}]
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config(self.config)

    def test_stop_limit_out_of_range_is_rejected(self) -> None:
        self.config["bus"]["stops"] = [{"id": "1", "name": "Stop", "limit": 0}]
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config(self.config)

    def test_boolean_coordinate_is_rejected(self) -> None:
        self.config["flights"]["location"]["lat"] = True
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config(self.config)

    def test_out_of_range_coordinate_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.config)
        invalid["weather"]["location"]["latitude"] = 91
        with self.assertRaises(config_validator.ConfigError):
            config_validator.validate_config(invalid)

    def test_invalid_json_cli_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            path.write_text("{", encoding="utf-8")
            self.assertEqual(config_validator.main([str(path)]), 1)

    def test_missing_file_cli_returns_nonzero(self) -> None:
        self.assertEqual(config_validator.main(["/nonexistent/config.json"]), 1)


if __name__ == "__main__":
    unittest.main()
