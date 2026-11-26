"""index/card_lastmod.json must match cards_by_id + the image manifest.

If this fails, run `python3 scripts/update_card_lastmod.py` and commit the result.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_card_lastmod_is_current():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "update_card_lastmod.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
