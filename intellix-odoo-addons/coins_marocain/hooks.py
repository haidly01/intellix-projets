# -*- coding: utf-8 -*-
"""Post-init : migrer niveau_visibilite → categories multi-valeurs."""


def _cat(env, code):
    return env["coins.property.category"].sudo().search([("code", "=", code)], limit=1)


def post_init_hook(env):
    Cat = env["coins.property.category"].sudo()
    if not Cat.search_count([]):
        return
    Prop = env["coins.property"].sudo()
    by_code = {c.code: c for c in Cat.search([])}

    for prop in Prop.search([]):
        if prop.category_ids:
            continue
        codes = []
        # Ancien champ stocké avant compute (lecture SQL si besoin)
        raw = prop.niveau_visibilite
        if raw == "public":
            codes.append("decouverte")
        elif raw == "privatisation":
            codes.append("privatisation")
        pillar = prop.map_pillar or ""
        if pillar == "villas_riads":
            codes.append("hebergement")
        elif pillar == "bien_etre":
            codes.append("bien_etre")
        elif pillar == "evenements":
            codes.append("evenements")
        cats = Cat.browse([by_code[c].id for c in codes if c in by_code])
        vals = {"category_ids": [(6, 0, cats.ids)]}
        if "hebergement" in codes:
            vals["location_chambre_unite"] = True
        prop.write(vals)
