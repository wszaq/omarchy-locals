"""Tests for autostart list + recipe persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lib import model, persist


class AutostartPersistTests(unittest.TestCase):
    def test_set_and_load_autostart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autostart.json"
            ok, result = persist.set_autostart("docker:pg", True, path=path)
            self.assertTrue(ok)
            self.assertTrue(result["autostart"])
            ids, errs = persist.load_autostart(path)
            self.assertEqual(errs, [])
            self.assertEqual(ids, ["docker:pg"])
            ok, result = persist.set_autostart("port:3000", True, path=path)
            self.assertTrue(ok)
            ids, _ = persist.load_autostart(path)
            self.assertEqual(ids, ["docker:pg", "port:3000"])
            ok, _ = persist.set_autostart("docker:pg", False, path=path)
            self.assertTrue(ok)
            ids, _ = persist.load_autostart(path)
            self.assertEqual(ids, ["port:3000"])

    def test_missing_autostart_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            ids, errs = persist.load_autostart(path)
            self.assertEqual(ids, [])
            self.assertEqual(errs, [])

    def test_recipe_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipes = Path(tmp)
            ok, _ = persist.save_recipe(
                "port:11434",
                argv=["ollama", "serve"],
                cwd="/tmp",
                comm="ollama",
                port=11434,
                recipes_dir=recipes,
            )
            self.assertTrue(ok)
            recipe = persist.load_recipe("port:11434", recipes_dir=recipes)
            self.assertIsNotNone(recipe)
            self.assertEqual(recipe["argv"], ["ollama", "serve"])
            self.assertEqual(recipe["cwd"], "/tmp")

    def test_annotate_adds_start_when_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipes = Path(tmp)
            persist.save_recipe(
                "port:8080",
                argv=["python", "-m", "http.server", "8080"],
                cwd="/tmp",
                port=8080,
                recipes_dir=recipes,
            )
            status = model.build_status(
                [{"id": "port:8080", "kind": "port", "label": ":8080", "port": 8080, "discovered": True}],
                docker_reachable=False,
                port_probes={"port:8080": {"listening": False}},
            )
            persist.set_autostart("port:8080", True, path=Path(tmp) / "autostart.json")
            # annotate with empty autostart list but recipe present
            annotated = persist.annotate_status_rows(
                status, autostart_ids=[], recipes_dir=recipes
            )
            row = annotated["targets"][0]
            self.assertTrue(row["hasRecipe"])
            self.assertTrue(row["canAutostart"])
            self.assertIn("start", row["actions"])
            self.assertEqual(row["state"], "stopped")

    def test_can_autostart_denies_docker_proxy(self):
        row = {
            "kind": "port",
            "meta": {"dockerBacked": True, "pid": 9, "canRestart": True},
        }
        self.assertFalse(persist.can_autostart_row(row, has_recipe=True))

    def test_docker_can_autostart(self):
        row = {"kind": "docker", "meta": {"container": "pg"}}
        self.assertTrue(persist.can_autostart_row(row, has_recipe=False))


if __name__ == "__main__":
    unittest.main()
