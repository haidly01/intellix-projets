# -*- coding: utf-8 -*-
"""Créer Excursion Agafay dans Odoo (odoo-bin shell)."""

Prop = env["coins.property"]  # noqa: F821
Cat = env["coins.property.category"]  # noqa: F821
Video = env["coins.fiche_video"]  # noqa: F821

# Catégorie expériences (idempotent)
cat_exp = Cat.search([("code", "=", "experiences")], limit=1)
if not cat_exp:
    cat_exp = Cat.create(
        {
            "name": "Expériences",
            "code": "experiences",
            "sequence": 55,
            "description": "Activités et expériences — filtre carte Marrakech en vidéo.",
        }
    )
    print("CREATED category experiences", cat_exp.id)
else:
    print("category experiences", cat_exp.id)

existing = Prop.search([("name", "ilike", "Excursion Agafay")], limit=1)
prop = existing if existing else None
if prop:
    print("UPDATE existing", prop.id)
else:
    print("CREATE new")

desc = """
<p><strong>Agafay à moins de 400&nbsp;dh</strong> — chameau, quad, repas, animation, transport… tout est inclus, tu n’as rien à organiser.</p>
<p>On te prend en charge le temps d’une journée dans le désert, à deux pas de Marrakech.</p>
<p>Écris-nous <strong>AGAFAY</strong> en message pour réserver ta place.</p>
""".strip()

narrative = """
<p>Journée désert d’Agafay tout inclus à moins de 400&nbsp;dh : chameau, quad, repas, animation et transport. Réserve en écrivant AGAFAY.</p>
""".strip()

codes = ["decouverte", "experiences"]
cat_ids = Cat.search([("code", "in", codes)]).ids

vals = {
    "name": "Excursion Agafay",
    "property_type": "other",
    "state": "active",
    "city": "Marrakech",
    "district": "Désert d’Agafay",
    "street": "Agafay, près de Marrakech",
    "latitude": 31.5050,
    "longitude": -8.0700,
    "map_zone": "agafay",
    "map_pillar": "experiences",
    "category_ids": [(6, 0, cat_ids)],
    "niveau_visibilite": "public",
    "description": desc,
    "narrative": narrative,
}

if prop:
    prop.write(vals)
else:
    prop = Prop.create(vals)
print("property", prop.id, prop.name, prop.category_codes)

video_url = "https://coinsmarocain.com/assets/video/excursion-agafay.mp4"
vid = Video.search([("fiche_id", "=", prop.id)], limit=1)
vvals = {
    "fiche_id": prop.id,
    "titre": "Agafay à moins de 400 dh — tout inclus",
    "video_url": video_url,
    "statut": "publiee",
    "ordre_affichage": 5,
}
if "source" in Video._fields:
    vvals["source"] = "proprietaire"
if vid:
    vid.write(vvals)
else:
    vid = Video.create(vvals)
print("video", vid.id, vid.statut, vid.video_url)

if hasattr(prop, "is_carte_public"):
    print("is_carte_public", prop.is_carte_public())

env.cr.commit()  # noqa: F821
print("COMMITTED id=%s" % prop.id)
