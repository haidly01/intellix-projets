# -*- coding: utf-8 -*-
import json
from decimal import Decimal


def json_dumps_safe(data):
    """Sérialise un dict Odoo en JSON (gère Decimal MySQL)."""

    def _default(obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        raise TypeError(
            f"Object of type {type(obj).__name__} is not JSON serializable"
        )

    return json.dumps(data, default=_default)
