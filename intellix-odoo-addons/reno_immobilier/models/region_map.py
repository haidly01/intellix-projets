# -*- coding: utf-8 -*-
"""Ville / texte libre → région administrative du Québec.

Sert uniquement la matrice lacunes du tableau de bord. Ne remplace pas
la couverture GPS / rayon de renovation_conciergerie.
"""
import re
import unicodedata

# Colonnes de la maquette → noms renovation.service.category
MATRIX_SERVICES = (
    ("toiture", "Toiture", ("Toiture",)),
    ("isolation", "Isolation", ("Isolation",)),
    ("thermopompe", "Thermopompe", ("Thermopompe",)),
    ("portes", "Portes / fenêtres", ("Portes et fenetres", "Portes et fenêtres")),
    ("cuisine", "Cuisine / SDB", ("Cuisine et salle de bain",)),
    ("fondations", "Fondations", ("Fondations",)),
    ("plomberie", "Plomberie", ("Plomberie",)),
    ("electricite", "Électricité", ("Electricite", "Électricité")),
    ("peinture", "Peinture", ("Peinture",)),
)

REGION_ESTRIE = "Estrie"
REGION_MONTEREGIE = "Montérégie"
REGION_LAURENTIDES = "Laurentides"
REGION_MONTREAL = "Montréal"
REGION_QUEBEC = "Québec (ville)"
REGION_LAVAL = "Laval"
REGION_LANAUDIERE = "Lanaudière"
REGION_OUTAOUAIS = "Outaouais"
REGION_CAPITALE = REGION_QUEBEC
REGION_MAURICIE = "Mauricie"
REGION_CENTRE = "Centre-du-Québec"
REGION_CHAUDIERE = "Chaudière-Appalaches"
REGION_SAGUENAY = "Saguenay–Lac-Saint-Jean"
REGION_BAS_SL = "Bas-Saint-Laurent"
REGION_COTE_NORD = "Côte-Nord"
REGION_GASPE = "Gaspésie–Îles-de-la-Madeleine"
REGION_ABITIBI = "Abitibi-Témiscamingue"
REGION_NORD = "Nord-du-Québec"

ALL_QC_REGIONS = (
    REGION_MONTREAL,
    REGION_LAVAL,
    REGION_LAURENTIDES,
    REGION_LANAUDIERE,
    REGION_MONTEREGIE,
    REGION_ESTRIE,
    REGION_QUEBEC,
    REGION_CHAUDIERE,
    REGION_MAURICIE,
    REGION_CENTRE,
    REGION_OUTAOUAIS,
    REGION_SAGUENAY,
    REGION_BAS_SL,
    REGION_COTE_NORD,
    REGION_GASPE,
    REGION_ABITIBI,
    REGION_NORD,
)

# Alias de région (texte partenaire / lead) → libellé canonique
_REGION_ALIASES = {
    "estrie": REGION_ESTRIE,
    "cantons de l est": REGION_ESTRIE,
    "cantons-de-l'est": REGION_ESTRIE,
    "monteregie": REGION_MONTEREGIE,
    "rive sud": REGION_MONTEREGIE,
    "rive-sud": REGION_MONTEREGIE,
    "laurentides": REGION_LAURENTIDES,
    "laurentide": REGION_LAURENTIDES,
    "montreal": REGION_MONTREAL,
    "ile de montreal": REGION_MONTREAL,
    "grand montreal": REGION_MONTREAL,
    "quebec": REGION_QUEBEC,
    "quebec ville": REGION_QUEBEC,
    "ville de quebec": REGION_QUEBEC,
    "capitale nationale": REGION_QUEBEC,
    "capitale-nationale": REGION_QUEBEC,
    "laval": REGION_LAVAL,
    "lanaudiere": REGION_LANAUDIERE,
    "outaouais": REGION_OUTAOUAIS,
    "gatineau": REGION_OUTAOUAIS,
    "mauricie": REGION_MAURICIE,
    "centre du quebec": REGION_CENTRE,
    "chaudiere appalaches": REGION_CHAUDIERE,
    "saguenay": REGION_SAGUENAY,
    "saguenay lac saint jean": REGION_SAGUENAY,
    "bas saint laurent": REGION_BAS_SL,
    "cote nord": REGION_COTE_NORD,
    "gaspesie": REGION_GASPE,
    "abitibi": REGION_ABITIBI,
    "abitibi temiscamingue": REGION_ABITIBI,
    "nord du quebec": REGION_NORD,
}

# Villes fréquentes (leads / partenaires Réno). Clé = texte normalisé.
_CITY_TO_REGION = {
    # Montréal
    "montreal": REGION_MONTREAL,
    "montréal": REGION_MONTREAL,
    "westmount": REGION_MONTREAL,
    "outremont": REGION_MONTREAL,
    "verdun": REGION_MONTREAL,
    "lasalle": REGION_MONTREAL,
    "lachine": REGION_MONTREAL,
    "anjou": REGION_MONTREAL,
    "saint leonard": REGION_MONTREAL,
    "st leonard": REGION_MONTREAL,
    "montreal nord": REGION_MONTREAL,
    "montreal est": REGION_MONTREAL,
    "cote saint luc": REGION_MONTREAL,
    "hampstead": REGION_MONTREAL,
    "mont royal": REGION_MONTREAL,
    "ville mont royal": REGION_MONTREAL,
    "dollard des ormeaux": REGION_MONTREAL,
    "pointe claire": REGION_MONTREAL,
    "dorval": REGION_MONTREAL,
    "kirkland": REGION_MONTREAL,
    "beaconsfield": REGION_MONTREAL,
    "pierrefonds": REGION_MONTREAL,
    "saint laurent": REGION_MONTREAL,
    "st laurent": REGION_MONTREAL,
    "ile bizard": REGION_MONTREAL,
    "sainte genevieve": REGION_MONTREAL,
    "montreal ouest": REGION_MONTREAL,
    "cote des neiges": REGION_MONTREAL,
    "ndg": REGION_MONTREAL,
    "notre dame de grace": REGION_MONTREAL,
    "plateau": REGION_MONTREAL,
    "rosemont": REGION_MONTREAL,
    "hochelaga": REGION_MONTREAL,
    "mercier qc": REGION_MONTEREGIE,
    # Laval
    "laval": REGION_LAVAL,
    "chomedey": REGION_LAVAL,
    "duvernay": REGION_LAVAL,
    "vimont": REGION_LAVAL,
    "fabreville": REGION_LAVAL,
    "sainte dorothee": REGION_LAVAL,
    "laval des rapides": REGION_LAVAL,
    "pont viau": REGION_LAVAL,
    # Laurentides
    "saint jerome": REGION_LAURENTIDES,
    "st jerome": REGION_LAURENTIDES,
    "sainte therese": REGION_LAURENTIDES,
    "ste therese": REGION_LAURENTIDES,
    "blainville": REGION_LAURENTIDES,
    "boisbriand": REGION_LAURENTIDES,
    "mirabel": REGION_LAURENTIDES,
    "rosemere": REGION_LAURENTIDES,
    "lorraine": REGION_LAURENTIDES,
    "bois des filion": REGION_LAURENTIDES,
    "sainte anne des plaines": REGION_LAURENTIDES,
    "saint eustache": REGION_LAURENTIDES,
    "st eustache": REGION_LAURENTIDES,
    "deux montagnes": REGION_LAURENTIDES,
    "saint sauveur": REGION_LAURENTIDES,
    "sainte adele": REGION_LAURENTIDES,
    "sainte agathe": REGION_LAURENTIDES,
    "sainte agathe des monts": REGION_LAURENTIDES,
    "val david": REGION_LAURENTIDES,
    "mont tremblant": REGION_LAURENTIDES,
    "labelle": REGION_LAURENTIDES,
    "mont laurier": REGION_LAURENTIDES,
    "sainte sophie": REGION_LAURENTIDES,
    "prevost": REGION_LAURENTIDES,
    "saint colomban": REGION_LAURENTIDES,
    "morin heights": REGION_LAURENTIDES,
    "piedmont": REGION_LAURENTIDES,
    "sainte anne des lacs": REGION_LAURENTIDES,
    "sainte marthe sur le lac": REGION_LAURENTIDES,
    "oka": REGION_LAURENTIDES,
    "saint joseph du lac": REGION_LAURENTIDES,
    "gore": REGION_LAURENTIDES,
    "brownsburg": REGION_LAURENTIDES,
    "lachute": REGION_LAURENTIDES,
    # Montérégie
    "longueuil": REGION_MONTEREGIE,
    "brossard": REGION_MONTEREGIE,
    "saint lambert": REGION_MONTEREGIE,
    "boucherville": REGION_MONTEREGIE,
    "saint bruno": REGION_MONTEREGIE,
    "saint bruno de montarville": REGION_MONTEREGIE,
    "sainte julie": REGION_MONTEREGIE,
    "varennes": REGION_MONTEREGIE,
    "chambly": REGION_MONTEREGIE,
    "carignan": REGION_MONTEREGIE,
    "saint jean sur richelieu": REGION_MONTEREGIE,
    "st jean": REGION_MONTEREGIE,
    "candiac": REGION_MONTEREGIE,
    "la prairie": REGION_MONTEREGIE,
    "delson": REGION_MONTEREGIE,
    "sainte catherine": REGION_MONTEREGIE,
    "saint constant": REGION_MONTEREGIE,
    "chateauguay": REGION_MONTEREGIE,
    "beauharnois": REGION_MONTEREGIE,
    "salaberry de valleyfield": REGION_MONTEREGIE,
    "valleyfield": REGION_MONTEREGIE,
    "saint hyacinthe": REGION_MONTEREGIE,
    "beloeil": REGION_MONTEREGIE,
    "mont saint hilaire": REGION_MONTEREGIE,
    "otterburn park": REGION_MONTEREGIE,
    "saint basile le grand": REGION_MONTEREGIE,
    "sorel": REGION_MONTEREGIE,
    "sorel tracy": REGION_MONTEREGIE,
    "granby": REGION_MONTEREGIE,
    "acton vale": REGION_MONTEREGIE,
    "vaudreuil": REGION_MONTEREGIE,
    "vaudreuil dorion": REGION_MONTEREGIE,
    "saint lazare": REGION_MONTEREGIE,
    "pincourt": REGION_MONTEREGIE,
    "ile perrot": REGION_MONTEREGIE,
    "saint zotique": REGION_MONTEREGIE,
    "rigaud": REGION_MONTEREGIE,
    "chambly": REGION_MONTEREGIE,
    "richelieu": REGION_MONTEREGIE,
    "marieville": REGION_MONTEREGIE,
    "farnham": REGION_MONTEREGIE,
    "cowansville": REGION_ESTRIE,
    "bromont": REGION_ESTRIE,
    "sutton": REGION_ESTRIE,
    "lac brome": REGION_ESTRIE,
    "knowlton": REGION_ESTRIE,
    # Estrie
    "sherbrooke": REGION_ESTRIE,
    "magog": REGION_ESTRIE,
    "orford": REGION_ESTRIE,
    "north hatley": REGION_ESTRIE,
    "waterville": REGION_ESTRIE,
    "coaticook": REGION_ESTRIE,
    "eastman": REGION_ESTRIE,
    "windsor": REGION_ESTRIE,
    "richmond": REGION_ESTRIE,
    "val des sources": REGION_ESTRIE,
    "asbestos": REGION_ESTRIE,
    "lac megantic": REGION_ESTRIE,
    "east angus": REGION_ESTRIE,
    "weedon": REGION_ESTRIE,
    "windsor": REGION_ESTRIE,
    "lennoxville": REGION_ESTRIE,
    "rock forest": REGION_ESTRIE,
    "fleurimont": REGION_ESTRIE,
    "ashton": REGION_ESTRIE,
    # Québec (ville) / Capitale-Nationale
    "quebec": REGION_QUEBEC,
    "quebec city": REGION_QUEBEC,
    "sainte foy": REGION_QUEBEC,
    "beauport": REGION_QUEBEC,
    "charlesbourg": REGION_QUEBEC,
    "sillery": REGION_QUEBEC,
    "cap rouge": REGION_QUEBEC,
    "loretteville": REGION_QUEBEC,
    "val belair": REGION_QUEBEC,
    "vanier": REGION_QUEBEC,
    "lebourgneuf": REGION_QUEBEC,
    "l ancienne lorette": REGION_QUEBEC,
    "ancienne lorette": REGION_QUEBEC,
    "saint augustin de desmaures": REGION_QUEBEC,
    "lac beauport": REGION_QUEBEC,
    "stoneham": REGION_QUEBEC,
    "shannon": REGION_QUEBEC,
    "wendake": REGION_QUEBEC,
    "boischatel": REGION_QUEBEC,
    "l ange gardien": REGION_QUEBEC,
    "chateaunricher": REGION_QUEBEC,
    # Chaudière-Appalaches
    "levis": REGION_CHAUDIERE,
    "saint lambert de lauzon": REGION_CHAUDIERE,
    "saint etienne": REGION_CHAUDIERE,
    "saint etienne de lauzon": REGION_CHAUDIERE,
    "saint nicolas": REGION_CHAUDIERE,
    "saint romuald": REGION_CHAUDIERE,
    "charny": REGION_CHAUDIERE,
    "saint jean chrysostome": REGION_CHAUDIERE,
    "thetford mines": REGION_CHAUDIERE,
    "sainte marie": REGION_CHAUDIERE,
    "montmagny": REGION_CHAUDIERE,
    # Lanaudière
    "terrebonne": REGION_LANAUDIERE,
    "mascouche": REGION_LANAUDIERE,
    "repentigny": REGION_LANAUDIERE,
    "l assomption": REGION_LANAUDIERE,
    "assomption": REGION_LANAUDIERE,
    "joliette": REGION_LANAUDIERE,
    "rawdon": REGION_LANAUDIERE,
    "saint charles borromee": REGION_LANAUDIERE,
    "charlemagne": REGION_LANAUDIERE,
    "lavaltrie": REGION_LANAUDIERE,
    "berthierville": REGION_LANAUDIERE,
    "saint lin laurentides": REGION_LANAUDIERE,
    # Outaouais
    "gatineau": REGION_OUTAOUAIS,
    "hull": REGION_OUTAOUAIS,
    "aylmer": REGION_OUTAOUAIS,
    "gatineau hull": REGION_OUTAOUAIS,
    "chelsea": REGION_OUTAOUAIS,
    "wakefield": REGION_OUTAOUAIS,
    "val des monts": REGION_OUTAOUAIS,
    "maniwaki": REGION_OUTAOUAIS,
    # Mauricie / Centre
    "trois rivieres": REGION_MAURICIE,
    "shawinigan": REGION_MAURICIE,
    "louiseville": REGION_MAURICIE,
    "drummondville": REGION_CENTRE,
    "victoriaville": REGION_CENTRE,
    "becancour": REGION_CENTRE,
    "nicolet": REGION_CENTRE,
    # Saguenay
    "saguenay": REGION_SAGUENAY,
    "chicoutimi": REGION_SAGUENAY,
    "jonquiere": REGION_SAGUENAY,
    "la baie": REGION_SAGUENAY,
    "alma": REGION_SAGUENAY,
    "roberval": REGION_SAGUENAY,
    "saint honore": REGION_SAGUENAY,
    # Autres
    "rimouski": REGION_BAS_SL,
    "riviere du loup": REGION_BAS_SL,
    "baie comeau": REGION_COTE_NORD,
    "sept iles": REGION_COTE_NORD,
    "gaspe": REGION_GASPE,
    "perce": REGION_GASPE,
    "rouyn noranda": REGION_ABITIBI,
    "val d or": REGION_ABITIBI,
    "amos": REGION_ABITIBI,
}

_PROVINCE_WIDE = {
    "toute la province",
    "tout le quebec",
    "province",
    "multi region",
    "multi regions",
    "multiregion",
    "province de quebec",
    "partout au quebec",
    "tout qc",
    "toute la province de quebec",
}

_SPLIT = re.compile(r"[,;/\n|]+")


def fold_text(value):
    text = unicodedata.normalize("NFKD", (value or "").strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def normalize_service_name(value):
    return fold_text(value)


# Catégories parentes du module conciergerie → colonnes de la matrice uniquement.
_PARENT_SERVICE_KEYS = {
    "renovation interieure": ("cuisine", "plomberie", "electricite", "peinture"),
    "renovation exterieure": ("toiture", "fondations"),
    "renovation ecoenergy": ("isolation", "thermopompe", "portes"),
    "salle de bain": ("cuisine",),
}

def service_aliases():
    mapping = {}
    for key, _label, names in MATRIX_SERVICES:
        for name in names:
            mapping[normalize_service_name(name)] = key
        mapping[key] = key
    return mapping


def service_keys_from_names(names):
    alias = service_aliases()
    keys = set()
    for name in names or []:
        folded = normalize_service_name(name)
        if folded in _PARENT_SERVICE_KEYS:
            keys.update(_PARENT_SERVICE_KEYS[folded])
            continue
        mapped = alias.get(folded)
        if mapped:
            keys.add(mapped)
    return keys


def tokens_from_text(value):
    raw = (value or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in _SPLIT.split(raw) if p.strip()]
    return parts or [raw]


def resolve_region_token(value):
    key = fold_text(value)
    if not key:
        return None
    if key in _PROVINCE_WIDE:
        return "QC"
    if key in _REGION_ALIASES:
        return _REGION_ALIASES[key]
    if key in _CITY_TO_REGION:
        return _CITY_TO_REGION[key]
    words = key.split()
    for city, region in _CITY_TO_REGION.items():
        if len(city) >= 4 and (key.startswith(city + " ") or city in words):
            return region
    for alias, region in _REGION_ALIASES.items():
        if len(alias) >= 8 and alias in key:
            return region
    return None


def regions_from_texts(*values):
    found = []
    seen = set()
    for value in values:
        for token in tokens_from_text(value):
            region = resolve_region_token(token)
            if region == "QC":
                return list(ALL_QC_REGIONS)
            if region and region not in seen:
                seen.add(region)
                found.append(region)
    return found


def lead_region(city, extra=None):
    regions = regions_from_texts(city, extra)
    if not regions:
        return None
    return regions[0]


def format_pct(value):
    return ("%0.1f" % (value or 0.0)).replace(".", ",") + " %"


def plural_leads(n):
    n = int(n or 0)
    return "%s lead" % n if n == 1 else "%s leads" % n


def period_days_label(date_from, date_to):
    if not date_from or not date_to:
        return "période"
    delta = (date_to - date_from).days + 1
    if delta <= 0:
        return "période"
    return "%sj" % delta


def build_recruitment_callout(rows, services, period_label, unmapped_leads=0):
    """Texte FR dérivé des trous réels. Jamais le paragraphe illustratif de la maquette."""
    gaps = []
    empty_regions = []
    for row in rows:
        lead_n = int(row.get("leads") or 0)
        gap_services = [
            cell["label"]
            for cell in row.get("cells") or []
            if cell.get("tone") == "gap"
        ]
        if lead_n > 0 and len(gap_services) == len(services):
            empty_regions.append((lead_n, row["name"], gap_services))
        if lead_n > 0:
            for cell in row.get("cells") or []:
                if cell.get("tone") == "gap":
                    gaps.append((lead_n, row["name"], cell["label"]))

    bits = []
    if empty_regions:
        empty_regions.sort(key=lambda i: (-i[0], i[1]))
        for lead_n, name, _svcs in empty_regions[:3]:
            bits.append(
                "%s n’a aucun partenaire, toutes catégories confondues, malgré %s sur %s."
                % (name, plural_leads(lead_n), period_label)
            )

    used_pairs = {(name, None) for _n, name, _s in empty_regions}
    extra = []
    for lead_n, name, service in sorted(gaps, key=lambda i: (-i[0], i[1], i[2])):
        if (name, None) in used_pairs:
            continue
        pair = (name, service)
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        extra.append(
            "%s est absent en %s malgré %s dans cette région."
            % (service, name, plural_leads(lead_n))
        )
        if len(extra) >= 3:
            break
    bits.extend(extra)

    if not bits:
        if rows:
            title = "Priorité de recrutement"
            body = (
                "Aucun trou service × région avec des leads sur %s. "
                "Les cases vides sans leads restent à surveiller, mais ne justifient pas un recrutement immédiat."
                % period_label
            )
        else:
            title = "Priorité de recrutement"
            body = (
                "Pas encore de croisement exploitable : aucun lead géolocalisé ni partenaire "
                "actif à projeter sur la matrice pour %s."
                % period_label
            )
    else:
        title = "Priorité de recrutement"
        body = " ".join(bits)
        body += (
            " Recruter précisément sur ces croisements — pas un appel générique « on manque de monde »."
        )

    if unmapped_leads:
        body += (
            " %s sans ville classée : renseigner la ville du lead pour affiner la matrice."
            % plural_leads(unmapped_leads)
        )
    return {"title": title, "body": body}
