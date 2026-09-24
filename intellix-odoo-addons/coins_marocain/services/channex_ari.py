# -*- coding: utf-8 -*-
"""ARI Channex — payloads batchés (full sync + deltas). Jamais une boucle date → 1 POST.

Full sync certif : toutes les chambres et tous les plans partagent le même
date_from et le même date_to (500 jours). Les variations passent par `days`,
jamais par une deuxième fenêtre.

L'application déclare min stay arrival + through, max stay, CTA, CTD et
stop sell : chaque objet restrictions du full sync doit porter ces clés.
"""
from datetime import date, timedelta


DECLARED_RESTRICTION_KEYS = (
    "min_stay_arrival",
    "min_stay_through",
    "max_stay",
    "closed_to_arrival",
    "closed_to_departure",
    "stop_sell",
)

_RESTRICTION_META_KEYS = {
    "property_id",
    "rate_plan_id",
    "date",
    "date_from",
    "date_to",
    "days",
}


def _ymd(d):
    return d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]


def task_ids(body):
    data = (body or {}).get("data") if isinstance(body, dict) else body
    if not isinstance(data, list):
        data = [data] if data else []
    return [row.get("id") for row in data if isinstance(row, dict) and row.get("id")]


def date_range(date_from, date_to=None):
    """Plage fusionnée (date_from/date_to) — pas un objet `date` isolé."""
    start = _ymd(date_from)
    end = _ymd(date_to or date_from)
    if end < start:
        start, end = end, start
    return {"date_from": start, "date_to": end}


def restriction_defaults(**overrides):
    """Valeurs non nulles pour les restrictions déclarées (pas de clé absente)."""
    payload = {
        "min_stay_arrival": 1,
        "min_stay_through": 1,
        "max_stay": 30,
        "closed_to_arrival": False,
        "closed_to_departure": False,
        "stop_sell": False,
    }
    payload.update(overrides)
    return payload


def restriction_has_update(row):
    """True s'il y a un tarif ou une restriction à pousser (hors ids / dates)."""
    for key, value in (row or {}).items():
        if key in _RESTRICTION_META_KEYS:
            continue
        if value is None or value == "":
            continue
        return True
    return False


def _range_bounds(row):
    if row.get("date_from"):
        start = _ymd(row["date_from"])
        end = _ymd(row.get("date_to") or row["date_from"])
        if end < start:
            start, end = end, start
        return start, end
    day = row.get("date")
    if not day:
        return None
    value = _ymd(day)
    return value, value


def merge_availability_values(values):
    """Regroupe dates isolées et plages consécutives (même qty / room) en date_from/date_to."""
    if not values:
        return []
    grouped = {}
    leftovers = []
    for raw in values:
        row = dict(raw or {})
        bounds = _range_bounds(row)
        if not bounds:
            leftovers.append(row)
            continue
        key = (
            row.get("property_id"),
            row.get("room_type_id"),
            int(row.get("availability") or 0),
            tuple(row.get("days") or ()),
        )
        grouped.setdefault(key, []).append(bounds)

    merged = list(leftovers)
    for (prop, room, avail, days), ranges in grouped.items():
        ordered = sorted(ranges)
        run_start, run_end = ordered[0]
        for start, end in ordered[1:]:
            gap = (date.fromisoformat(start) - date.fromisoformat(run_end)).days
            if gap <= 1:
                if end > run_end:
                    run_end = end
                continue
            item = {
                "property_id": prop,
                "room_type_id": room,
                "availability": avail,
            }
            item.update(date_range(run_start, run_end))
            if days:
                item["days"] = list(days)
            merged.append(item)
            run_start, run_end = start, end
        item = {
            "property_id": prop,
            "room_type_id": room,
            "availability": avail,
        }
        item.update(date_range(run_start, run_end))
        if days:
            item["days"] = list(days)
        merged.append(item)
    return merged


def build_full_sync_availability(property_id, twin_id, double_id, start, days=500):
    """500 jours alignés, inventaire type hôtel. 1 payload /availability."""
    window = date_range(start, start + timedelta(days=days - 1))
    return [
        {
            "property_id": property_id,
            "room_type_id": twin_id,
            "availability": 8,
            **window,
        },
        {
            "property_id": property_id,
            "room_type_id": twin_id,
            "days": ["fr", "sa"],
            "availability": 5,
            **window,
        },
        {
            "property_id": property_id,
            "room_type_id": double_id,
            "availability": 4,
            **window,
        },
        {
            "property_id": property_id,
            "room_type_id": double_id,
            "days": ["fr", "sa", "su"],
            "availability": 2,
            **window,
        },
    ]


def build_full_sync_restrictions(property_id, plans, start, days=500):
    """500 jours alignés pour les 4 plans. Variations via days uniquement.

    plans = dict title -> rate_plan_id
      Twin BAR, Twin BB, Double BAR, Double BB

    Chaque objet porte les 6 restrictions déclarées (valeurs non nulles).
    """
    window = date_range(start, start + timedelta(days=days - 1))

    def row(plan_key, **extra):
        payload = {
            "property_id": property_id,
            "rate_plan_id": plans[plan_key],
        }
        payload.update(window)
        payload.update(restriction_defaults())
        payload.update(extra)
        return payload

    weekend = restriction_defaults(min_stay_arrival=2, min_stay_through=2)
    return [
        row("twin_bar", rate="129.00"),
        row("twin_bar", days=["fr"], rate="149.00", **weekend),
        row("twin_bar", days=["sa"], rate="169.00", **weekend),
        row("twin_bb", rate="154.00"),
        row("twin_bb", days=["fr"], rate="174.00", **weekend),
        row("twin_bb", days=["sa"], rate="194.00", **weekend),
        row("double_bar", rate="149.00"),
        row("double_bar", days=["fr"], rate="179.00", **weekend),
        row("double_bar", days=["sa"], rate="199.00", **weekend),
        row("double_bb", rate="179.00"),
        row("double_bb", days=["fr"], rate="209.00", **weekend),
        row("double_bb", days=["sa"], rate="229.00", **weekend),
    ]


def classify_room_type_note(note):
    """Mappe le libellé mapping → twin / double."""
    raw = (note or "").strip().lower()
    if "twin" in raw:
        return "twin"
    if "double" in raw:
        return "double"
    return None


def classify_rate_plan_note(note):
    """Mappe le libellé mapping → clé full sync (twin_bar / twin_bb / …)."""
    raw = (note or "").strip().lower()
    is_twin = "twin" in raw
    is_double = "double" in raw
    is_bb = any(
        token in raw
        for token in ("breakfast", "b&b", "bb ", " bb", "petit-déj", "petit dej")
    )
    if is_twin and is_bb:
        return "twin_bb"
    if is_twin:
        return "twin_bar"
    if is_double and is_bb:
        return "double_bb"
    if is_double:
        return "double_bar"
    return None


def assert_full_sync_restrictions(rows):
    """Certif : même fenêtre + toutes les clés déclarées + rate sur chaque objet."""
    if not rows:
        raise ValueError("Full sync restrictions vide")
    starts = {row.get("date_from") for row in rows}
    ends = {row.get("date_to") for row in rows}
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError(
            "Full sync dates non alignées: start=%s end=%s" % (sorted(starts), sorted(ends))
        )
    required = ("rate",) + DECLARED_RESTRICTION_KEYS
    for index, row in enumerate(rows):
        missing = [key for key in required if row.get(key) in (None, "")]
        if missing:
            raise ValueError("Full sync objet %s sans %s" % (index, missing))
    return rows
