"""Offline checks that pre-submit validation preserves translation catalogs."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_validation_restores_catalogs_on_success_and_failure(self):
        for fail in ("", "makemessages", "compilemessages", "interrupted"):
            for existing_mo in (False, True):
                with self.subTest(fail=fail, existing_mo=existing_mo), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    catalogs = root / "locale/de/LC_MESSAGES"
                    catalogs.mkdir(parents=True)
                    (catalogs / "django.po").write_bytes(b"original po")
                    if existing_mo:
                        (catalogs / "django.mo").write_bytes(b"original mo")
                    scripts = root / ".bash_scripts"
                    scripts.mkdir()
                    for name in ("check_translations.sh", "check_translation_catalogs.sh"):
                        path = scripts / name
                        path.write_text("#!/bin/sh\nexit 0\n")
                        path.chmod(0o755)
                    script = scripts / "pre_commit_check.sh"
                    script.write_text((ROOT / "backend/.bash_scripts/pre_commit_check.sh").read_text().replace("/opt/mrmap", str(root)))
                    binary = root / "bin"
                    binary.mkdir()
                    (binary / "flake8").write_text("#!/bin/sh\nexit 0\n")
                    (binary / "flake8").chmod(0o755)
                    python = binary / "python"
                    python.write_text(
                        "#!/bin/sh\n"
                        'case "$2" in\n'
                        f'  makemessages) printf regenerated > "{catalogs}/django.po" ;;\n'
                        f'  compilemessages) printf regenerated > "{catalogs}/django.mo" ;;\n'
                        'esac\n'
                        'if [ "$FAIL_COMMAND" = interrupted ] && [ "$2" = makemessages ]; then kill -TERM "$PPID"; fi\n'
                        '[ "$2" != "$FAIL_COMMAND" ]\n')
                    python.chmod(0o755)
                    env = {**os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
                           "FAIL_COMMAND": fail}
                    result = subprocess.run(["sh", str(script)], cwd=root, env=env, capture_output=True)
                    expected = 143 if fail == "interrupted" else 1 if fail else 0
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual((catalogs / "django.po").read_bytes(), b"original po")
                    if existing_mo:
                        self.assertEqual((catalogs / "django.mo").read_bytes(), b"original mo")
                    else:
                        self.assertFalse((catalogs / "django.mo").exists())
                    self.assertEqual(list(catalogs.glob("*.bak")), [])


if __name__ == "__main__":
    unittest.main()
