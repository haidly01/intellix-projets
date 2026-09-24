# -*- coding: utf-8 -*-
"""Tague les 27 photos de La Casa Ysabella. Les autres lieux restent sans tag."""
from odoo import SUPERUSER_ID, api

# ids Odoo photo → codes (classement visuel du 5 sept 2026)
YSABELLA_PHOTO_CATEGORIES = {
    50: ["aires_communes"],
    51: ["aires_communes"],
    52: ["restauration"],
    53: ["aires_communes"],
    54: ["aires_communes"],
    55: ["aires_communes"],
    56: ["aires_communes"],
    57: ["restauration", "aires_communes"],
    58: ["restauration"],
    59: ["restauration"],
    60: ["restauration"],
    61: ["restauration"],
    62: ["restauration", "aires_communes"],
    63: ["restauration"],
    64: ["aires_communes"],
    27: ["chambres"],
    28: ["chambres"],
    29: ["chambres"],
    32: ["chambres"],
    33: ["chambres"],
    35: ["chambres"],
    36: ["chambres"],
    37: ["chambres"],
    38: ["chambres"],
    42: ["chambres"],
    43: ["chambres"],
    46: ["chambres"],
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Cat = env["coins.property.photo.category"]
    Photo = env["coins.property.photo"]
    by_code = {c.code: c.id for c in Cat.search([])}
    if not by_code:
        return
    for photo_id, codes in YSABELLA_PHOTO_CATEGORIES.items():
        photo = Photo.browse(photo_id)
        if not photo.exists():
            continue
        ids = [by_code[c] for c in codes if c in by_code]
        if photo.room_id and by_code.get("chambres") and by_code["chambres"] not in ids:
            ids = [by_code["chambres"]] + ids
        photo.category_ids = [(6, 0, ids)]
