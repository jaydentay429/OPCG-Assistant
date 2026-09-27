"""OP18-112 Yamakaji: standard Blocker, no other effect."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if "battle" not in sys.modules:
    pkg = types.ModuleType("battle")
    pkg.__path__ = [str(ROOT / "battle")]
    sys.modules["battle"] = pkg

from battle.effects import has_blocker  # noqa: E402
from battle.state import CardInst  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def test_op18_112_is_standard_blocker():
    info = dict(_CARDS["OP18-112"])
    assert info["name"] == "火燒山"
    assert info["name_en"] == "Yamakaji"
    assert info["card_type"] == "Character"
    assert info["cost"] == 7
    assert info["power"] == 7000
    assert info["counter"] == 2000
    assert "中將" in info["traits"]
    assert "海軍" in info["traits"]
    inst = CardInst(iid="yk", card_id="OP18-112", rested=False, summoning_sick=False)
    assert has_blocker(info, inst) is True
    assert "【防禦】" in str(info.get("effect") or "")
