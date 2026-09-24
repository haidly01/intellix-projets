#!/usr/bin/env python3
"""SEO Lots 2–5: thin FR/EN content, forfaits rename, TEMP-ia swap."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- Lot 2/3 enrichment blocks (id=seo-extra) ---

FR_ACTIVITES = {
    "desert-agafay.html": """
      <h2>Agafay dans un séjour privatisé</h2>
      <p>Beaucoup de groupes placent Agafay la veille d'un dîner en villa ou le lendemain d'une arrivée aéroport : assez proche pour ne pas fatiguer, assez dépaysant pour marquer le séjour. En privatisation, le camp et le créneau sont réservés pour vous — pas de mixage avec un circuit bas de gamme.</p>
      <p>Pensez aussi à l'enchainement avec un <a href="/activites/hammam-traditionnel">hammam</a> le lendemain, ou une soirée <a href="/activites/visite-medina-nuit">médina de nuit</a> si vous voulez contrastes urbains et désert dans la même semaine. Demande de devis via <a href="/contact">contact</a> ou WhatsApp Yasmine.</p>
""",
    "vallee-ourika.html": """
      <h2>Ourika pour les groupes et les familles</h2>
      <p>La vallée se prête bien aux journées actives sans engagement trek : pauses photo, thé, cascades selon le niveau. Pour un team building soft ou une retraite, on évite les créneaux trop chargés et on privilégie un guide qui parle la langue du groupe.</p>
      <p>À combiner avec un hébergement privatisé sur la <a href="/carte/hebergement">carte hébergement</a> ou un retour détente <a href="/carte/bien-etre">bien-être</a>. Comparatif désert vs montagne : <a href="/blog/agafay-ou-ourika-comparatif">Agafay ou Ourika</a>.</p>
""",
    "visite-medina-nuit.html": """
      <h2>Médina de nuit et programme événementiel</h2>
      <p>Une visite nocturne ouvre souvent un weekend EVJF, un voyage de noces ou une retraite courte : le groupe se retrouve, le guide fixe le rythme, et chacun garde une première image forte de Marrakech. On peut enchaîner rooftop ou dîner selon l'énergie du soir.</p>
      <p>Pour le shopping artisanat en journée, voir aussi les <a href="/guide-marrakech/souks-marrakech">souks</a> dans le <a href="/guide-marrakech">guide des escapades</a>. Réservation privée via <a href="/activites">le catalogue</a> ou <a href="/contact">devis</a>.</p>
""",
    "cours-cuisine-marocaine.html": """
      <h2>Cuisine locale et privatisation</h2>
      <p>L'atelier fonctionne particulièrement bien en villa ou riad : le chef se déplace, ou le groupe rejoint une maison partenaire. Moins de logistique que plusieurs restaurants, plus de lien entre les participants — utile pour EVJF, anniversaire ou kick-off d'équipe.</p>
      <p>Complétez par la <a href="/carte/route-gourmande">route gourmande</a> ou un <a href="/activites/hammam-traditionnel">hammam</a>. Devis : <a href="/contact">nous contacter</a>.</p>
""",
    "hammam-traditionnel.html": """
      <h2>Bien-être sans catalogue anonyme</h2>
      <p>Nous distinguons hammam traditionnel et instituts / spas contemporains. Le premier est un rituel ; les seconds offrent protocoles plus longs, couples ou groupes selon l'adresse. Dans les deux cas, la réservation passe par un interlocuteur unique pour éviter les créneaux saturés.</p>
      <p>Parcourir les pins <a href="/carte/bien-etre">bien-être en vidéo</a>, ou combiner avec une <a href="/journee-piscine">journée piscine</a> et un hébergement de la <a href="/villas-riads-marrakech">sélection villas &amp; riads</a>.</p>
""",
    "balade-cheval-palmeraie.html": """
      <h2>Palmeraie et rythme du séjour</h2>
      <p>La balade à cheval reste une parenthèse courte : idéale le matin avant une journée médina, ou en fin d'après-midi avant un dîner. Les centres partenaires sont choisis pour l'encadrement et le respect des animaux — pas pour le volume touristique.</p>
      <p>Autres idées nature : <a href="/activites/vallee-ourika">Ourika</a>, <a href="/guide-marrakech/imlil">Imlil</a>, <a href="/activites/desert-agafay">Agafay</a>. Vue d'ensemble dans le <a href="/guide-marrakech">guide escapades</a>.</p>
""",
}

FR_EVT = {
    "mariages.html": """
      <h2>Invités, hébergement et timing</h2>
      <p>Au-delà de la cérémonie, la friction vient souvent des chambres, des transferts et du brunch du lendemain. Nous proposons un lieu principal privatisé et, si besoin, des villas satellites dans le même quartier. Le fil WhatsApp reste unique pour le couple et le wedding planner.</p>
      <p>Inspirations : <a href="/blog/tendances-mariage-2026-2027">tendances mariage</a>, <a href="/carte">lieux en vidéo</a>, <a href="/villas-riads-marrakech">villas &amp; riads</a>.</p>
""",
    "team-building-retraites.html": """
      <h2>Cadre de travail et respirations</h2>
      <p>Une retraite utile alterne plages de travail (salle, Wi-Fi, lumière) et sorties courtes qui ne dispersent pas le groupe. Agafay sunset, Ourika demi-journée ou médina de nuit se calent sans transformer le séjour en circuit touristique.</p>
      <p>Voir <a href="/blog/team-building-marrakech-riad-privatise">team building en riad</a> et <a href="/evenements">le hub événements</a>.</p>
""",
    "evjf-evg.html": """
      <h2>Construire le weekend sans catalogue générique</h2>
      <p>Nous partons du profil du groupe (âge, énergie, budget, intimité) pour proposer un fil conducteur : villa piscine, 1001 nuits, ou mix hammam + médina. L'objectif est un lieu privatisé et des prestataires déjà éprouvés — pas une liste de 30 activités à arbitrer seule.</p>
      <p>Détails : <a href="/evenements/evjf-villa-piscine">villa piscine</a>, <a href="/evenements/evjf-1001-nuits">1001 nuits</a>, <a href="/contact">devis</a>.</p>
""",
    "anniversaires.html": """
      <h2>Du dîner intimiste au weekend</h2>
      <p>Selon l'effectif, on privilégie rooftop + nuitées, ou un domaine avec brunch. La surprise reste discrète : le lieu n'est pas publié sur les plateformes grand public. Yasmine aligne traiteur, musique et éventuellement photographe local.</p>
      <p>Lire <a href="/blog/feter-anniversaire-marrakech-riad-privatise">fêter un anniversaire en riad</a> · <a href="/villas-riads-marrakech">hébergements</a>.</p>
""",
    "galas-levees-de-fonds.html": """
      <h2>Protocole et confidentialité</h2>
      <p>Les comités demandent souvent une régie sobre, un accueil VIP et un espace partenaires sans transformer le lieu en salon d'hôtel. Nous vérifions capacités réelles, flux et contraintes de voisinage avant de présenter 2–3 options seulement.</p>
      <p>Checklist : <a href="/blog/organiser-evenement-reussi-checklist">événement réussi</a> · <a href="/evenements">hub événements</a>.</p>
""",
    "evjf-1001-nuits.html": """
      <h2>Scénographie et lieu</h2>
      <p>Le thème 1001 nuits fonctionne quand l'architecture porte déjà lanternes, textiles et patios — pas quand on « décore par-dessus » un espace neutre. Nous sélectionnons des salons capables d'accueillir musique live discrète et dîner assis.</p>
      <p>Retour hub <a href="/evenements/evjf-evg">EVJF / EVG</a> · <a href="/carte">carte vidéo</a>.</p>
""",
    "evjf-villa-piscine.html": """
      <h2>Musique, voisinage et capacité</h2>
      <p>Avant de confirmer une villa, on valide capacité réelle, règles de bruit et accès. Marrakech n'est pas uniforme : palmeraie, route de Fès ou centre n'offrent pas les mêmes contraintes. Le groupe garde un interlocuteur unique jusqu'au départ.</p>
      <p>Voir aussi <a href="/journee-piscine">journée piscine</a> et <a href="/evenements/evjf-evg">tous les formats EVJF</a>.</p>
""",
}

FR_CARTE = {
    "hebergement.html": """
    <section id="seo-extra" class="wrap" style="max-width:720px;margin:8px auto 28px;padding:0 22px;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">Villas et riads en vidéo, pas en catalogue</h2>
      <p>Chaque pin hébergement ouvre une courte vidéo du lieu : lumière, volumes, outdoor. L'idée est de choisir avec le regard avant de demander une privatisation. Les adresses restent confidentielles — pas de listing exhaustif type plateforme.</p>
      <p>Pour un devis : précisez dates, effectif et ambiance (médina, palmeraie, domaine). Compléments : <a href="/villas-riads-marrakech">page villas &amp; riads</a>, <a href="/evenements">événements</a>, <a href="/contact">contact</a>.</p>
    </section>
""",
    "bien-etre.html": """
    <section id="seo-extra" class="wrap" style="max-width:720px;margin:8px auto 28px;padding:0 22px;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">Bien-être sélectionné à Marrakech</h2>
      <p>Spas, hammams et instituts partenaires : on privilégie l'intimité, la qualité du soin et la possibilité de créneaux groupe ou couple. La carte vidéo montre le lieu ; Yasmine réserve le bon créneau.</p>
      <p>Liens utiles : <a href="/activites/hammam-traditionnel">hammam traditionnel</a>, <a href="/journee-piscine">journée piscine</a>, <a href="/carte/hebergement">hébergements</a>.</p>
    </section>
""",
    "route-gourmande.html": """
    <section id="seo-extra" class="wrap" style="max-width:720px;margin:8px auto 28px;padding:0 22px;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">Tables et expériences gourmandes</h2>
      <p>La route gourmande regroupe des adresses choisies pour le cadre autant que l'assiette — utiles pour un dîner d'événément, un déjeuner d'équipe ou une soirée EVJF. Vidéo courte pour sentir l'ambiance avant de réserver.</p>
      <p>Atelier cuisine : <a href="/activites/cours-cuisine-marocaine">cours de cuisine</a> · devis <a href="/contact">contact</a>.</p>
    </section>
""",
    "experiences.html": None,  # already has exp-seo; extend below
    "evenements.html": """
    <section id="seo-extra" class="wrap" style="max-width:720px;margin:8px auto 28px;padding:0 22px;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">Lieux pour mariages, retraites et célébrations</h2>
      <p>Ce thème carte regroupe des adresses capables d'accueillir un événement privatisé — pas seulement une nuitée. Capacités, outdoor et intimité se vérifient en vidéo avant le devis.</p>
      <p>Hub dédié : <a href="/evenements">événements</a> · <a href="/evenements/mariages">mariages</a> · <a href="/evenements/team-building-retraites">retraites</a>.</p>
    </section>
""",
}

EN_BLOCKS = {
    "en/events/weddings.html": """
      <h2>Guests, stays and timing</h2>
      <p>Beyond the ceremony, friction often comes from rooms, transfers and the next-day brunch. We propose one privatised main venue and, if needed, satellite villas nearby — with a single WhatsApp thread for the couple and planner.</p>
      <p>See also the <a href="/en/map">video map</a> and <a href="/en/villas-riads">villas &amp; riads</a>.</p>
""",
    "en/events/hen-stag.html": """
      <h2>Build the weekend without a generic catalogue</h2>
      <p>We start from the group's profile — energy, budget, privacy — then propose a clear thread: pool villa, 1001 Nights salon, or hammam + medina. One privatised place beats thirty options to arbitrate alone.</p>
      <p>Details: <a href="/en/events/hen-stag-villa-pool">villa pool</a>, <a href="/en/events/hen-stag-1001-nights">1001 Nights</a>, <a href="/en/contact">contact</a>.</p>
""",
    "en/events/hen-stag-1001-nights.html": """
      <h2>Staging that fits the architecture</h2>
      <p>1001 Nights works when the venue already carries lanterns, textiles and patios — not when décor is pasted onto a neutral room. We shortlist salons that can host discreet live music and a seated dinner.</p>
      <p>Back to <a href="/en/events/hen-stag">hen &amp; stag</a> · <a href="/en/map">video map</a>.</p>
""",
    "en/events/hen-stag-villa-pool.html": """
      <h2>Music, neighbours and real capacity</h2>
      <p>Before confirming a villa we check true capacity, noise rules and access. Palmeraie, route de Fès and the centre do not share the same constraints. The group keeps one contact until departure.</p>
      <p>See <a href="/en/events/hen-stag">all hen &amp; stag formats</a>.</p>
""",
    "en/villas-riads.html": """
      <h2>Privatised stays, not hotel blocks</h2>
      <p>Our villas and riads are chosen for character and full privatisation — not for endless availability. Short videos on the map help you shortlist before asking for dates and a quote.</p>
      <p>Browse the <a href="/en/map/stay">stay map</a> or request a <a href="/en/contact">custom quote</a>.</p>
""",
    "en/map/experiences.html": """
    <section id="seo-extra" style="max-width:40rem;margin:28px 0;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">Experiences beyond the medina</h2>
      <p>Agafay, Ourika, night medina walks, cooking classes and hammams complete a privatised stay. This map theme gathers outdoor and cultural experiences we trust — without budget group tours.</p>
      <p>French deep-dives: <a href="/activites/desert-agafay">Agafay</a>, <a href="/activites/vallee-ourika">Ourika</a>, <a href="/guide-marrakech">day-trip guide</a>.</p>
    </section>
""",
}

EN_MAP_INTRO = """
    <section id="seo-extra" class="wrap" style="max-width:720px;margin:8px auto 28px;padding:0 22px;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">Marrakech on video</h2>
      <p>Each pin opens a short film of a partner place — light, volumes, outdoor. Choose with your eyes before requesting privatisation. Addresses stay confidential; we never publish a full public directory.</p>
      <p>Related: <a href="/en/villas-riads">villas &amp; riads</a>, <a href="/en/events">events</a>, <a href="/en/contact">contact</a>.</p>
    </section>
"""

HUB_ACTIVITES_EXTRA = """
  <section id="seo-extra-2" class="wrap" style="max-width:720px;margin:12px auto 32px;padding:0 22px;color:#262220;line-height:1.65">
    <h2 style="font-family:Cardo,Georgia,serif;font-size:1.4rem">Formats privés, un seul interlocuteur</h2>
    <p>Que vous prépariez un voyage en couple, un EVJF ou une retraite d'équipe, les expériences se réservent en privé : transport, guide, timing alignés sur votre hébergement. Le <a href="/guide-marrakech">guide des escapades</a> relie médina, désert, Atlas et océan ; la <a href="/carte">carte en vidéo</a> montre les lieux.</p>
    <p>Questions fréquentes : demi-journée vs journée, niveau de marche, régimes alimentaires, créneaux hammam — chaque fiche activité répond point par point. Sinon, <a href="/contact">écrivez-nous</a>.</p>
  </section>
"""

CONTACT_EXTRA = """
      <aside id="seo-extra-2" style="max-width:640px;margin:0 auto 28px;padding:0 4px;line-height:1.65;color:#262220">
        <h2 style="font-family:Cardo,Georgia,serif;font-size:1.35rem">Ce que nous organisons le plus souvent</h2>
        <p>Privatisation de villa ou riad, mariage intime, retraite / team building, EVJF, demi-journée Agafay ou Ourika, médina de nuit, hammam. Indiquez dates et taille de groupe : nous répondons avec 1–2 pistes concrètes plutôt qu'un catalogue.</p>
        <p>Parcourir : <a href="/carte">Marrakech en vidéo</a> · <a href="/evenements">événements</a> · <a href="/guide-marrakech">escapades</a> · <a href="/villas-riads-marrakech">villas &amp; riads</a>.</p>
      </aside>
"""

TEMP_SWAP = {
    "TEMP-ia-mariages-01": "/assets/img/forfaits-hero",
    "TEMP-ia-mariages-02": "/assets/img/couple",
    "TEMP-ia-team-building-01": "/assets/img/surmesure",
    "TEMP-ia-evjf-01": "/assets/img/forfaits-hero",
    "TEMP-ia-evjf-1001-01": "/assets/img/hero",
    "TEMP-ia-evjf-villa-01": "/assets/img/forfaits-hero",
    "TEMP-ia-anniversaires-01": "/assets/img/couple",
    "TEMP-ia-galas-01": "/assets/img/partenaire",
    "TEMP-ia-villas-riads-01": "/assets/img/forfaits-hero",
    "TEMP-ia-selection-01": "/assets/img/partenaire",
}


def inject_before(html: str, marker: str, block: str) -> str:
    if "id=\"seo-extra\"" in html or "id='seo-extra'" in html:
        if block and "id=\"seo-extra\"" in block:
            return html  # already has
    if marker not in html:
        return html
    return html.replace(marker, block + marker, 1)


def enrich_activites() -> None:
    for fname, block in FR_ACTIVITES.items():
        path = ROOT / "activites" / fname
        t = path.read_text(encoding="utf-8")
        if "Agafay dans un séjour privatisé" in t or "Ourika pour les groupes" in t or "Médina de nuit et programme" in t or "Cuisine locale et privatisation" in t or "Bien-être sans catalogue" in t or "Palmeraie et rythme" in t:
            print("skip act", fname)
            continue
        t2 = inject_before(t, '<div class="article-cta">', block)
        if t2 == t:
            t2 = inject_before(t, '<div class="article-cta">', block)
        path.write_text(t2, encoding="utf-8")
        print("act", fname)


def enrich_hub_contact() -> None:
    hub = ROOT / "activites.html"
    h = hub.read_text(encoding="utf-8")
    if "seo-extra-2" not in h:
        # after first seo section or before filters
        if 'id="activites-seo"' in h:
            h = h.replace(
                '</section>\n\n  <section class="filters"',
                '</section>\n' + HUB_ACTIVITES_EXTRA + '\n  <section class="filters"',
                1,
            )
        else:
            h = inject_before(h, '<section class="filters"', HUB_ACTIVITES_EXTRA)
        hub.write_text(h, encoding="utf-8")
        print("hub activites")
    # experiences already has exp-seo — append
    exp = ROOT / "carte" / "experiences.html"
    e = exp.read_text(encoding="utf-8")
    if "id=\"seo-extra\"" not in e and "Pour un événement ou une retraite" in e:
        extra = """
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.3rem;margin-top:1.2em">Réserver une expérience privée</h2>
      <p>Chaque sortie se calcule avec votre hébergement et votre énergie du jour. Yasmine propose un créneau et un prestataire — vous validez. Guide transversal : <a href="/guide-marrakech">idées d'escapades</a>.</p>
"""
        e = e.replace(
            "voir <a href=\"/evenements\">événements</a> et <a href=\"/contact\">contact</a>.</p>",
            "voir <a href=\"/evenements\">événements</a> et <a href=\"/contact\">contact</a>.</p>" + extra,
            1,
        )
        exp.write_text(e, encoding="utf-8")
        print("experiences+")
    ct = ROOT / "contact.html"
    c = ct.read_text(encoding="utf-8")
    if "seo-extra-2" not in c:
        c = c.replace('<main class="ct-main">', '<main class="ct-main">\n' + CONTACT_EXTRA, 1)
        # fix villas link if old forfaits in contact-seo
        c = c.replace('href="/forfaits"', 'href="/villas-riads-marrakech"')
        ct.write_text(c, encoding="utf-8")
        print("contact+")


def enrich_events_fr() -> None:
    for fname, block in FR_EVT.items():
        path = ROOT / "evenements" / fname
        t = path.read_text(encoding="utf-8")
        key = block.strip().split("\n", 1)[0]
        if key.strip() in t:
            print("skip evt", fname)
            continue
        marker = '      </div>\n      <aside class="pillar-aside">'
        t2 = inject_before(t, marker, block)
        path.write_text(t2, encoding="utf-8")
        print("evt", fname)


def enrich_carte_fr() -> None:
    for fname, block in FR_CARTE.items():
        if not block:
            continue
        path = ROOT / "carte" / fname
        t = path.read_text(encoding="utf-8")
        if 'id="seo-extra"' in t:
            print("skip carte", fname)
            continue
        # insert after intro section closes — before toolbar
        marker = '    <div class="cm-carte-toolbar">'
        if marker in t:
            t = t.replace(marker, block + "\n" + marker, 1)
        else:
            t = inject_before(t, '<footer', block)
        path.write_text(t, encoding="utf-8")
        print("carte", fname)


def enrich_en() -> None:
    for rel, block in EN_BLOCKS.items():
        path = ROOT / rel
        if not path.exists():
            print("missing", rel)
            continue
        t = path.read_text(encoding="utf-8")
        if "id=\"seo-extra\"" in block and 'id="seo-extra"' in t:
            print("skip en", rel)
            continue
        key = re.sub(r"<[^>]+>", "", block.strip().split("\n", 1)[0])[:40]
        if key and key in t:
            print("skip en", rel)
            continue
        if rel.endswith("experiences.html"):
            t = inject_before(t, '<div class="cm-plein-air-actions">', block)
        elif "pillar-aside" in t:
            t = inject_before(t, '      </div>\n      <aside class="pillar-aside">', block)
        elif 'class="pillar-main"' in t:
            t = inject_before(t, '</div>\n      <aside', block)
        else:
            t = inject_before(t, "<footer", block)
        # villas page may differ
        if rel.endswith("villas-riads.html") and block not in t:
            t = path.read_text(encoding="utf-8")
            if "Privatised stays" not in t:
                t = inject_before(t, "<footer", f"<main>{block}</main>\n") if "<footer" in t else t + block
        path.write_text(t, encoding="utf-8")
        print("en", rel)

    for rel in ["en/map.html", "en/map/index.html", "en/map/stay.html", "en/map/wellness.html", "en/map/food.html", "en/map/events.html"]:
        path = ROOT / rel
        if not path.exists():
            continue
        t = path.read_text(encoding="utf-8")
        if 'id="seo-extra"' in t:
            print("skip map", rel)
            continue
        marker = '    <div class="cm-carte-toolbar">'
        if marker in t:
            t = t.replace(marker, EN_MAP_INTRO + "\n" + marker, 1)
            path.write_text(t, encoding="utf-8")
            print("en map", rel)


def rename_forfaits() -> None:
    src = ROOT / "forfaits.html"
    dst = ROOT / "villas-riads-marrakech.html"
    html = src.read_text(encoding="utf-8")
    html = html.replace("https://coinsmarocain.com/forfaits", "https://coinsmarocain.com/villas-riads-marrakech")
    html = html.replace('href="/forfaits"', 'href="/villas-riads-marrakech"')
    html = html.replace(
        "<title>Forfaits Riads, Villas, piscines, rooftop, massages &amp; hammam | Coins Marocain Marrakech</title>",
        "<title>Villas &amp; riads à Marrakech — privatisation | Coins Marocain</title>",
    )
    html = html.replace(
        'content="Nos forfaits à Marrakech : riads, villas, piscines, rooftop, massages et hammam — réservez en ligne ou demandez un devis."',
        'content="Villas et riads privatissables à Marrakech : sélection vidéo, piscine, rooftop, bien-être. Devis sur mesure avec Yasmine."',
    )
    dst.write_text(html, encoding="utf-8")
    # stub redirect page at old URL (backup if nginx late)
    stub = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Redirection…</title>
  <meta name="robots" content="noindex,follow">
  <link rel="canonical" href="https://coinsmarocain.com/villas-riads-marrakech">
  <meta http-equiv="refresh" content="0;url=/villas-riads-marrakech">
  <script>location.replace("/villas-riads-marrakech");</script>
</head>
<body><p><a href="/villas-riads-marrakech">Villas &amp; riads à Marrakech</a></p></body>
</html>
"""
    src.write_text(stub, encoding="utf-8")
    print("wrote villas-riads-marrakech.html + forfaits stub")

    # lang-map
    lm = ROOT / "assets" / "lang-map.js"
    t = lm.read_text(encoding="utf-8")
    if "/villas-riads-marrakech" not in t:
        t = t.replace('"/forfaits": "/en/villas-riads"', '"/villas-riads-marrakech": "/en/villas-riads",\n    "/forfaits": "/en/villas-riads"')
        t = t.replace('"/en/villas-riads": "/forfaits"', '"/en/villas-riads": "/villas-riads-marrakech"')
        lm.write_text(t, encoding="utf-8")
        print("lang-map")

    # nav secondary forfaits → new
    nav = ROOT / "assets" / "nav.js"
    nt = nav.read_text(encoding="utf-8")
    nt2 = nt.replace('href: "/forfaits"', 'href: "/villas-riads-marrakech"')
    # ensureFooterLinks map
    if 'href: "/forfaits"' in nt2 or "/forfaits" in nt2:
        nt2 = nt2.replace(
            '{ href: "/forfaits", re: /\\/forfaits\\/?$/ },',
            '{ href: "/villas-riads-marrakech", re: /\\/(forfaits|villas-riads-marrakech)\\/?$/ },',
        )
    nav.write_text(nt2, encoding="utf-8")
    print("nav")

    # bulk replace internal links (not stub, not proof)
    for p in ROOT.rglob("*.html"):
        if "proof" in p.parts or "proofs" in p.parts:
            continue
        if p.name == "forfaits.html":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        new = text.replace('href="/forfaits"', 'href="/villas-riads-marrakech"')
        new = new.replace("href='/forfaits'", "href='/villas-riads-marrakech'")
        new = new.replace('href="forfaits"', 'href="/villas-riads-marrakech"')
        new = new.replace("https://coinsmarocain.com/forfaits\"", "https://coinsmarocain.com/villas-riads-marrakech\"")
        if new != text:
            p.write_text(new, encoding="utf-8")

    # sitemap
    sm = ROOT / "sitemap.xml"
    s = sm.read_text(encoding="utf-8")
    if "villas-riads-marrakech" not in s:
        s = s.replace(
            "<loc>https://coinsmarocain.com/forfaits</loc>",
            "<loc>https://coinsmarocain.com/villas-riads-marrakech</loc>",
        )
        s = s.replace(
            'hreflang="fr" href="https://coinsmarocain.com/forfaits"',
            'hreflang="fr" href="https://coinsmarocain.com/villas-riads-marrakech"',
        )
        s = s.replace(
            'hreflang="x-default" href="https://coinsmarocain.com/forfaits"',
            'hreflang="x-default" href="https://coinsmarocain.com/villas-riads-marrakech"',
        )
        sm.write_text(s, encoding="utf-8")
        print("sitemap")

    # nginx local conf
    ng = ROOT / "nginx-seo-redirects.conf"
    ngt = ng.read_text(encoding="utf-8")
    if "villas-riads-marrakech" not in ngt:
        block = """
location = /villas-riads-marrakech {
    try_files /villas-riads-marrakech.html =404;
}
location = /villas-riads-marrakech/ { return 301 https://coinsmarocain.com/villas-riads-marrakech; }
location = /forfaits { return 301 https://coinsmarocain.com/villas-riads-marrakech; }
location = /forfaits/ { return 301 https://coinsmarocain.com/villas-riads-marrakech; }
location = /forfaits.html { return 301 https://coinsmarocain.com/villas-riads-marrakech; }
"""
        ng.write_text(ngt + "\n" + block, encoding="utf-8")
        print("nginx conf append")


def swap_temp_ia() -> None:
    # money pages: evenements + forfaits/villas + notre-selection
    targets = list((ROOT / "evenements").glob("*.html"))
    targets += [
        ROOT / "villas-riads-marrakech.html",
        ROOT / "en" / "villas-riads.html",
    ]
    targets += list((ROOT / "en" / "events").glob("*.html"))
    targets += list((ROOT / "notre-selection").glob("*.html"))
    for path in targets:
        if not path.exists():
            continue
        t = path.read_text(encoding="utf-8")
        orig = t
        for temp, real in TEMP_SWAP.items():
            t = t.replace(f"/assets/img/ia/{temp}.jpg", f"{real}.jpg")
            t = t.replace(f"/assets/img/ia/{temp}.webp", f"{real}.webp")
            t = t.replace(f"https://coinsmarocain.com/assets/img/ia/{temp}.jpg", f"https://coinsmarocain.com{real}.jpg")
            t = t.replace(f'data-cm-ai-image="{temp}.jpg"', "")
            t = t.replace(f"data-cm-ai-image='{temp}.jpg'", "")
        # remove AI captions on money pages
        t = re.sub(
            r'\s*<figcaption class="cm-ai-caption">[^<]*</figcaption>',
            "",
            t,
        )
        t = t.replace("<!-- TEMP: image IA à remplacer -->\n", "")
        t = t.replace("<!-- TEMP: image IA à remplacer -->", "")
        # clean empty picture source if webp missing for some — keep jpg
        if t != orig:
            path.write_text(t, encoding="utf-8")
            print("temp-swap", path.relative_to(ROOT))


def wordcount_report() -> None:
    from html.parser import HTMLParser

    class T(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "nav", "header", "footer"):
                self.skip += 1

        def handle_endtag(self, tag):
            if tag in ("script", "style", "nav", "header", "footer") and self.skip:
                self.skip -= 1

        def handle_data(self, data):
            if not self.skip:
                self.parts.append(data)

    focus = []
    for pat in [
        "activites.html",
        "activites/*.html",
        "evenements/*.html",
        "carte/*.html",
        "contact.html",
        "villas-riads-marrakech.html",
        "en/villas-riads.html",
        "en/events/*.html",
        "en/map/*.html",
        "en/map.html",
    ]:
        focus += list(ROOT.glob(pat))
    thin = []
    ok = []
    for p in focus:
        if not p.is_file() or p.name in ("plein-air.html", "outdoors.html"):
            continue
        parser = T()
        parser.feed(p.read_text(encoding="utf-8", errors="ignore"))
        n = len(" ".join(parser.parts).split())
        rel = str(p.relative_to(ROOT))
        (thin if n < 400 else ok).append((n, rel))
    print("=== THIN ===")
    for n, r in sorted(thin):
        print(f"{n:4d} {r}")
    print("=== OK count", len(ok), "thin", len(thin))


def main() -> None:
    enrich_activites()
    enrich_hub_contact()
    enrich_events_fr()
    enrich_carte_fr()
    rename_forfaits()
    enrich_en()
    # re-run link fix after rename for enrichment blocks that used new slug
    swap_temp_ia()
    wordcount_report()


if __name__ == "__main__":
    main()
