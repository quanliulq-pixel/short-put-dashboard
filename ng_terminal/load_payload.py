# -*- coding: utf-8 -*-
"""Load / refresh Henry Hub NG dashboard payload for static terminal embed."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
SNAP = ROOT / "data" / "ng" / "last_dashboard.json"


def load_ng_payload(force: bool = False) -> dict:
    sys.path.insert(0, str(ROOT.parent))
    try:
        from ng_terminal import ng_dashboard  # type: ignore

        # ensure module writes under ng_terminal/data/ng
        data = ng_dashboard.build_dashboard(force=force)
        if isinstance(data, dict) and data.get("price"):
            SNAP.parent.mkdir(parents=True, exist_ok=True)
            SNAP.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
            return data
    except Exception as exc:
        logger.warning("NG live rebuild failed (%s); using snapshot", exc)

    if SNAP.exists():
        return json.loads(SNAP.read_text(encoding="utf-8"))
    return {
        "season_cn": "—",
        "updated_at": None,
        "composite_100": None,
        "confidence": None,
        "advice": {"bias_cn": "—", "action": "NG 数据暂不可用", "summary": ""},
        "price": {},
        "factors": [],
        "news": {},
        "events": [],
        "history": [],
        "errors": ["snapshot missing"],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = load_ng_payload(force=True)
    print("keys", sorted(p.keys())[:20], "composite", p.get("composite_100"))
