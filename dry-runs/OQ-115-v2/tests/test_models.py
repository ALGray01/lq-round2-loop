import tempfile
import unittest
from pathlib import Path

from router.models import RegistryError, load_registry


class TestModelRegistry(unittest.TestCase):
    def test_missing_registry_file_raises_clean_error_not_a_crash(self):
        # Regression: a round-3 attacker found a missing/corrupt models.json
        # produced a raw FileNotFoundError/JSONDecodeError traceback, the
        # same bug class already fixed for cap_state.json.
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "does_not_exist.json"
            with self.assertRaises(RegistryError):
                load_registry(missing_path)

    def test_malformed_registry_file_raises_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "models.json"
            bad_path.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(RegistryError):
                load_registry(bad_path)

    def test_empty_model_list_raises_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_path = Path(tmp) / "models.json"
            empty_path.write_text('{"models": []}', encoding="utf-8")
            with self.assertRaises(RegistryError):
                load_registry(empty_path)

    def test_loads_and_has_unique_ids(self):
        models = load_registry()
        self.assertGreaterEqual(len(models), 4)
        ids = [m.id for m in models]
        self.assertEqual(len(ids), len(set(ids)), "duplicate model ids in registry")

    def test_capability_tiers_in_range(self):
        for m in load_registry():
            for field in ("reasoning", "drafting", "factual_accuracy", "speed"):
                value = m.capability(field)
                self.assertGreaterEqual(value, 1)
                self.assertLessEqual(value, 5)


if __name__ == "__main__":
    unittest.main()
