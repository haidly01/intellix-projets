# -*- coding: utf-8 -*-
"""Créer Riad Ines dans Odoo (odoo-bin shell)."""

Prop = env["coins.property"]  # noqa: F821
Cat = env["coins.property.category"]  # noqa: F821
Video = env["coins.fiche_video"]  # noqa: F821
Room = env["coins.property.room"] if "coins.property.room" in env else None  # noqa: F821

existing = Prop.search([("name", "ilike", "Riad Ines")], limit=1)
prop = existing if existing else None
if prop:
    print("UPDATE existing", prop.id)
else:
    print("CREATE new")

desc = """
<p><strong>Riad Ines</strong></p>
<p>Niché à 20 minutes de Marrakech, au cœur d'une palmeraie d'oliviers centenaires,
le Riad Ines est une invitation à l'immersion marocaine authentique. Construit avec
amour par une famille sur 15 années, ce riad haut de gamme vient tout juste d'ouvrir
ses portes — un lieu rare, préservé, où chaque détail raconte un savoir-faire transmis.</p>
<p>Le riad compte 5 chambres et 2 suites avec vue sur la piscine, réparties dans un
cadre intime et chaleureux. Une immense piscine à débordement s'étend face aux
oliviers, offrant un cadre aussi apaisant que spectaculaire pour quelques jours de
détente ou un événement privé.</p>
<p><strong>Détails du lieu</strong></p>
<ul>
<li>5 chambres + 2 suites vue piscine</li>
<li>130&nbsp;€/nuit/chambre, petit-déjeuner inclus</li>
<li>Repas et collations traditionnels marocains disponibles</li>
<li>Immense piscine à débordement, jardin d'oliviers</li>
<li>Idéal pour événements privés ou séjours détente</li>
<li>À 20 minutes de Marrakech — parfait pour combiner avec vos activités
(désert, Ourika, médina…)</li>
</ul>
<p>Le Riad Ines, c'est l'âme du Maroc dans un écrin intime, pensé pour ceux qui
cherchent bien plus qu'un hébergement — une véritable expérience.</p>
""".strip()

narrative = """
<p>À 20 min de Marrakech, Riad Ines offre 5 chambres et 2 suites vue piscine dans
une palmeraie d'oliviers — hébergement, table marocaine et événements privés.</p>
""".strip()

codes = ["decouverte", "hebergement", "evenements", "route_gourmande"]
cat_ids = Cat.search([("code", "in", codes)]).ids

vals = {
    "name": "Riad Ines",
    "property_type": "riad",
    "state": "active",
    "city": "Aït Faska",
    "district": "RN9 — 20 min de Marrakech",
    "street": "RN9, 40000 Aït Faska",
    "latitude": 31.5742,
    "longitude": -7.7701,
    "map_zone": "autre",
    "map_pillar": "villas_riads",
    "category_ids": [(6, 0, cat_ids)],
    "niveau_visibilite": "public",
    "location_chambre_unite": True,
    "nb_suites": 7,
    "capacity": 14,
    "description": desc,
    "narrative": narrative,
}

# Route gourmande — repas / collations marocains sur place
if "rg_cuisine" in Prop._fields:
    vals["rg_cuisine"] = "marocaine_traditionnelle"
if "rg_cadre" in Prop._fields:
    vals["rg_cadre"] = "jardin,terrasse_exterieure"
if "rg_vue" in Prop._fields:
    vals["rg_vue"] = "jardin"
if "rg_ambiance" in Prop._fields:
    vals["rg_ambiance"] = "romantique"
if "rg_fourchette_prix" in Prop._fields:
    vals["rg_fourchette_prix"] = "milieu"
if "rg_privatisation_possible" in Prop._fields:
    vals["rg_privatisation_possible"] = True

if prop:
    prop.write(vals)
else:
    prop = Prop.create(vals)
print("property", prop.id, prop.name, prop.category_codes)

if Room is not None and not prop.room_ids:
    names = ["Chambre %d" % i for i in range(1, 6)] + [
        "Suite vue piscine 1",
        "Suite vue piscine 2",
    ]
    for name in names:
        rv = {"property_id": prop.id, "name": name}
        if "max_guests" in Room._fields:
            rv["max_guests"] = 2
        elif "capacity" in Room._fields:
            rv["capacity"] = 2
        Room.create(rv)
    print("rooms", prop.room_ids.mapped("name"))

video_url = "https://coinsmarocain.com/assets/video/riad-ines.mp4"
vid = Video.search([("fiche_id", "=", prop.id)], limit=1)
vvals = {
    "fiche_id": prop.id,
    "titre": "Riad Ines — Immersion marocaine authentique",
    "video_url": video_url,
    "statut": "publiee",
    "ordre_affichage": 10,
}
if "source" in Video._fields:
    vvals["source"] = "proprietaire"
if "snippet_url" in Video._fields:
    vvals["snippet_url"] = "https://coinsmarocain.com/assets/video/riad-ines-snippet.mp4"
if "poster_url" in Video._fields:
    vvals["poster_url"] = "https://coinsmarocain.com/assets/img/riad-ines-poster.jpg"

if vid:
    vid.write(vvals)
else:
    vid = Video.create(vvals)
print("video", vid.id, vid.statut, vid.video_url)

if hasattr(prop, "is_carte_public"):
    print("is_carte_public", prop.is_carte_public())

env.cr.commit()  # noqa: F821
print("COMMITTED id=%s" % prop.id)
