#!/usr/bin/env python3
"""Régénère /assets/taux.json (taux du jour, cache 24 h côté fichier + cron)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cm_fiche_devises import write_taux_json


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out",
        default="/var/www/coinsmarocain/assets/taux.json",
        help="Fichier JSON servi en /assets/taux.json et /api/taux.json",
    )
    args = p.parse_args()
    data = write_taux_json(Path(args.out))
    print(json.dumps({"out": args.out, "rates": data.get("rates"), "source": data.get("source")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
