"""Packaging checks with no Space account access or deployment side effects."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_space", ROOT / "tools/prepare_space.py")
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class SpacePackageTests(unittest.TestCase):
    def test_complete_allowlist_and_root_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = PACKAGE.stage(Path(temporary) / "space")
            self.assertEqual({p.name for p in target.iterdir()},
                             {*PACKAGE.FILES, "README.md", "tritowers_vision", "web"})
            self.assertEqual((target / "README.md").read_bytes(),
                             (ROOT / "README-SPACE.md").read_bytes())
            for name in PACKAGE.FILES:
                self.assertEqual((target / name).read_bytes(), (ROOT / name).read_bytes())
            self.assertTrue((target / "tritowers_vision/__init__.py").is_file())
            self.assertTrue((target / "tritowers_vision/data/font_glyphs.npz").is_file())
            self.assertFalse(list(target.rglob("*.pyc")))
            self.assertFalse(list(target.rglob("__pycache__")))
            metadata = (target / "README.md").read_text().split("---")[1]
            self.assertIn("sdk: gradio", metadata)
            self.assertIn("app_file: app.py", metadata)
            version = next(line.split(":", 1)[1].strip() for line in metadata.splitlines()
                           if line.startswith("sdk_version:"))
            self.assertIn("gradio==" + version, (target / "requirements.txt").read_text())

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            marker = target / "private.txt"
            marker.write_text("preserve")
            with self.assertRaises(ValueError):
                PACKAGE.stage(target)
            self.assertEqual(marker.read_text(), "preserve")

    def test_source_destination_rejected(self):
        with self.assertRaises(ValueError):
            PACKAGE.stage(ROOT / "staged-space")
        with self.assertRaises(ValueError):
            PACKAGE.stage(ROOT)

    def test_incomplete_source_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "space"
            with self.assertRaises(ValueError):
                PACKAGE.stage(target, source=temporary)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
