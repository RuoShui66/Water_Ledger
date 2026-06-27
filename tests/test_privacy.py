from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from water_ledger.privacy import scan_public_workspace


class PrivacyScanTest(unittest.TestCase):
    def test_skips_local_dependency_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret_name = "api" + "_key"
            secret_line = f"{secret_name} = 'not-a-real-key'\n"
            venv_file = root / ".venv" / "lib" / "site-packages" / "pkg.py"
            venv_file.parent.mkdir(parents=True)
            venv_file.write_text(secret_line, encoding="utf-8")

            public_file = root / "leaky.py"
            public_file.write_text(secret_line, encoding="utf-8")

            findings = scan_public_workspace(root)

        self.assertEqual([finding.path for finding in findings], ["leaky.py"])


if __name__ == "__main__":
    unittest.main()
