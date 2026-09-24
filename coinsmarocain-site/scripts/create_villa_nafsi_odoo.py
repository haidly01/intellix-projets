# -*- coding: utf-8 -*-
"""Créer Villa Nafsi dans Odoo (à lancer via odoo-bin shell)."""

Prop = env["coins.property"]  # noqa: F821
Cat = env["coins.property.category"]  # noqa: F821
Video = env["coins.fiche_video"]  # noqa: F821
Room = env["coins.property.room"] if "coins.property.room" in env else None  # noqa: F821

existing = Prop.search([("name", "ilike", "Nafsi")], limit=1)
if existing:
    prop = existing
    print("UPDATE existing", prop.id)
else:
    prop = None

desc = """
<p><strong>Villa Nafsi — Havre de paix face au Haut-Atlas</strong></p>
<p>Nichée dans un cadre rural calme et verdoyant, au cœur de la région d'Aghmat,
en direction de la vallée de l'Ourika, Villa Nafsi séduit par sa végétation
abondante et son atmosphère naturellement apaisante — le tout à seulement
30-35 minutes de Marrakech.</p>
<p><strong>Le logement</strong></p>
<p>La villa se déploie sur trois niveaux, pensés pour le confort et la
convivialité :</p>
<ul>
<li><strong>Rez-de-chaussée</strong> : une chambre double avec salle de bain
privative, la cuisine, la salle à manger, et une pièce modulable — salle de
jeux ou bureau, selon vos besoins.</li>
<li><strong>1er étage</strong> : quatre chambres doubles, une salle de bain,
un grand salon marocain, et un point d'eau pratique dans le couloir.</li>
<li><strong>2e étage</strong> : un rooftop aménagé, avec une vue dégagée et
imprenable sur le Haut-Atlas — parfait pour un café ou un dîner face aux
montagnes.</li>
</ul>
<p>À l'extérieur, un jardin arboré et un espace repas avec bar complètent ce
cadre paisible. La piscine, chauffée par pompe à chaleur, peut être sécurisée
pour les familles avec enfants.</p>
<p><strong>Votre séjour, en toute intimité</strong></p>
<p>Pendant votre séjour, la villa vous est entièrement privatisée : chambres,
espaces de vie, jardin, piscine et rooftop sont à votre usage exclusif. Le
gardien réside à proximité, dans un espace indépendant, et n'intervient que
sur demande ou en cas de besoin — pour préserver votre tranquillité.</p>
<p>Sur demande, nous organisons pour vous : cuisinière, transferts,
excursions.</p>
<p><strong>Le petit plus</strong></p>
<p>Chaque matin, un petit-déjeuner composé de produits frais et de saveurs
marocaines vous attend. Idéale pour un séjour en famille ou entre amis, Villa
Nafsi offre l'équilibre parfait entre proximité de Marrakech et véritable
évasion à la campagne.</p>
""".strip()

narrative = """
<p>Face au Haut-Atlas, à Aghmat / Ghmate, Villa Nafsi combine hébergement
privatisé et cadre événementiel intimiste : cinq chambres doubles, piscine
chauffée, jardin et rooftop — sans partager les lieux avec d'autres
voyageurs.</p>
""".strip()

codes = ["decouverte", "hebergement", "evenements", "privatisation"]
cat_ids = Cat.search([("code", "in", codes)]).ids

vals = {
    "name": "Villa Nafsi",
    "property_type": "villa",
    "state": "active",
    "city": "Ghmate",
    "district": "Aghmat — direction Ourika",
    "street": "Ghmate, Marrakesh-Safi, Maroc",
    "latitude": 31.4310,
    "longitude": -7.8020,
    "map_zone": "autre",
    "map_pillar": "villas_riads",
    "category_ids": [(6, 0, cat_ids)],
    "niveau_visibilite": "public",
    "location_chambre_unite": True,
    "nb_suites": 5,
    "capacity": 10,
    "description": desc,
    "narrative": narrative,
}

if prop:
    prop.write(vals)
else:
    prop = Prop.create(vals)
print("property", prop.id, prop.name, prop.category_codes)

if Room is not None and not prop.room_ids:
    room_vals_base = {"property_id": prop.id}
    for i in range(1, 6):
        rv = dict(room_vals_base, name="Chambre %d" % i)
        if "max_guests" in Room._fields:
            rv["max_guests"] = 2
        elif "capacity" in Room._fields:
            rv["capacity"] = 2
        Room.create(rv)
    print("rooms", prop.room_ids.mapped("name"))

video_url = "https://coinsmarocain.com/assets/video/villa-nafsi.mp4"
vid = Video.search([("fiche_id", "=", prop.id), ("video_url", "=", video_url)], limit=1)
vvals = {
    "fiche_id": prop.id,
    "titre": "Villa Nafsi — Havre de paix face à l'Atlas",
    "video_url": video_url,
    "statut": "publiee",
    "ordre_affichage": 10,
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
