#!/usr/bin/env python3
"""Generate /guide-marrakech hub + 6 destination pages (FR + EN)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_V = "cm109"

HEAD_COMMON = """  <meta charset="UTF-8">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" type="image/png" sizes="32x32" href="/assets/img/favicon-32.png">
  <link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Playfair+Display:ital,wght@0,500;1,500;1,600&family=Jost:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/activites.css?v={v}">
  <link rel="stylesheet" href="/assets/cm-chrome.css?v=cm108">
  <link rel="stylesheet" href="/assets/cookies.css?v=cm74">
  <link rel="stylesheet" href="/assets/guide-escapades.css?v={v}">
""".format(v=ASSET_V)

SCRIPTS = f"""  <script src="/assets/lang-map.js?v=cm74" defer></script>
  <script src="/assets/i18n.js?v=cm74" defer></script>
  <script src="/assets/nav.js?v={ASSET_V}" defer></script>
  <script src="/assets/cookies.js?v=cm74" defer></script>
"""

FOOTER_FR = """  <footer class="evt-footer cm-site-footer">
    <div class="wrap footer-cols">
      <div>
        <div class="logo">Coins <span>Marocain</span></div>
        <p class="foot-tag">Lieux confidentiels &amp; expériences à Marrakech.</p>
      </div>
      <div>
        <h4>Explorer</h4>
        <a href="/">Accueil</a>
        <a href="/evenements">Événements</a>
        <a href="/villas-riads-marrakech">Villas &amp; Riads</a>
        <a href="/activites">Expériences</a>
        <a href="/guide-marrakech">Guide des escapades</a>
        <a href="/blog/">Blogue</a>
        <a href="/partenaires">Partenaires</a>
        <a href="/carnet">Carnet</a>
      </div>
      <div>
        <h4>Services</h4>
        <a href="/wedding-planner">Wedding planner</a>
        <a href="/agence-de-voyage">Agence de voyage</a>
        <a href="/affiliation">Affiliation</a>
        <a href="/contact">Nous contacter</a>
        <a href="/confidentialite">Confidentialité &amp; cookies</a>
      </div>
    </div>
    <div class="wrap foot-bottom">
      <p>&copy; 2026 Coins Marocain — propriété de Digital Doorway SARL.</p>
    </div>
  </footer>
"""

FOOTER_EN = """  <footer class="evt-footer cm-site-footer">
    <div class="wrap footer-cols">
      <div>
        <div class="logo">Coins <span>Marocain</span></div>
        <p class="foot-tag">Curated places &amp; experiences in Marrakech.</p>
      </div>
      <div>
        <h4>Explore</h4>
        <a href="/en/">Home</a>
        <a href="/en/events">Events</a>
        <a href="/en/villas-riads">Villas &amp; Riads</a>
        <a href="/activites">Experiences</a>
        <a href="/en/guide-marrakech">Day-trip ideas</a>
        <a href="/en/blog/">Blog</a>
        <a href="/en/partners">Partners</a>
      </div>
      <div>
        <h4>Services</h4>
        <a href="/en/contact">Contact us</a>
        <a href="/confidentialite">Privacy &amp; cookies</a>
      </div>
    </div>
    <div class="wrap foot-bottom">
      <p>&copy; 2026 Coins Marocain — Digital Doorway SARL.</p>
    </div>
  </footer>
"""


def header(lang: str, fr_path: str, en_path: str) -> str:
    home = "/" if lang == "fr" else "/en/"
    fr_on = "on" if lang == "fr" else ""
    en_on = "on" if lang == "en" else ""
    aria = "Language" if lang == "en" else "Langue"
    open_lbl = "Open menu" if lang == "en" else "Ouvrir le menu"
    close_lbl = "Close menu" if lang == "en" else "Fermer le menu"
    return f"""  <header class="site-header" id="siteHeader">
    <div class="wrap header-inner">
      <a class="brand" href="{home}">
        <img src="/assets/img/logo-emblem-white.png?v=cm99" alt="Coins Marocain" class="brand-logo logo-light" width="168" height="104">
        <img src="/assets/img/logo-emblem.png?v=cm99" alt="Coins Marocain" class="brand-logo logo-dark" width="168" height="104">
      </a>
      <div class="header-actions">
        <div class="cm-lang-switch" role="group" aria-label="{aria}">
          <a href="{fr_path}" hreflang="fr" class="{fr_on}" data-lang-pref="fr">FR</a>
          <span aria-hidden="true">|</span>
          <a href="{en_path}" hreflang="en" class="{en_on}" data-lang-pref="en">EN</a>
        </div>
        <button class="burger" id="burger" aria-label="{open_lbl}"><span></span><span></span><span></span></button>
      </div>
    </div>
  </header>
  <nav class="menu-overlay" id="menuOverlay">
    <button class="menu-close" id="menuClose" aria-label="{close_lbl}">&times;</button>
    <p class="m-eyebrow">Coins Marocain</p>
  </nav>
"""


def cta(hook: str, btn: str = "Demander un devis", href: str = "/contact") -> str:
    return f"""  <aside class="cm-esc-cta" aria-label="Demande de devis">
    <div class="cm-esc-cta-inner">
      <div class="cm-esc-cta-copy">
        <h2>Envie d'organiser cette excursion&nbsp;?</h2>
        <p>{hook}</p>
      </div>
      <a class="btn" href="{href}">{btn}</a>
    </div>
  </aside>
"""


def cta_en(hook: str) -> str:
    return f"""  <aside class="cm-esc-cta" aria-label="Request a quote">
    <div class="cm-esc-cta-inner">
      <div class="cm-esc-cta-copy">
        <h2>Want to organise this outing?</h2>
        <p>{hook}</p>
      </div>
      <a class="btn" href="/en/contact">Request a quote</a>
    </div>
  </aside>
"""


def card(href: str, img: str, title: str, sub: str, badge: str = "") -> str:
    b = f'<span class="cm-esc-badge">{badge}</span>' if badge else ""
    return f"""          <a class="cm-esc-card" href="{href}">
            <div class="cm-esc-card-media" style="background-image:url('{img}')"></div>
            <div class="cm-esc-card-body">
              {b}
              <h3>{title}</h3>
              <p>{sub}</p>
            </div>
          </a>
"""


# Template extras for detail pages (does not alter drafted section copy).
DEST_META = {
    "essaouira": {
        "mid_img": "/assets/img/chefchaouen.jpg",
        "fr": {
            "bref": {
                "distance": "~2 h 30 de Marrakech",
                "format": "Journée",
                "ideal": "Océan, flânerie, kitesurf",
                "periode": "Toute l'année",
            },
            "quote": "« Perle bleue de l'Atlantique » — remparts face à l'océan, vents constants, rythme maritime.",
            "mid_caption": "Remparts et port d'Essaouira, face à l'Atlantique",
            "highlights": ["Citadelle", "Port & poisson grillé", "Surf & kitesurf"],
            "bref_labels": ("Distance", "Format", "Idéal pour", "Meilleure période"),
        },
        "en": {
            "bref": {
                "distance": "~2.5 h from Marrakech",
                "format": "Day trip",
                "ideal": "Ocean, wandering, kitesurf",
                "periode": "Year-round",
            },
            "quote": "“Blue Pearl of the Atlantic” — ramparts facing the ocean, steady winds, a maritime pace.",
            "mid_caption": "Essaouira ramparts and harbour on the Atlantic",
            "highlights": ["Citadel", "Port & grilled fish", "Surf & kitesurf"],
            "bref_labels": ("Distance", "Format", "Best for", "Best season"),
        },
    },
    "agadir": {
        "mid_img": "/assets/img/couple.jpg",
        "fr": {
            "bref": {
                "distance": "~3 h de Marrakech",
                "format": "Journée ou 2–3 nuits",
                "ideal": "Plage, repos, golf",
                "periode": "Toute l'année",
            },
            "quote": "Une vraie coupure balnéaire — pour prolonger un séjour à Marrakech sans repartir loin.",
            "mid_caption": "La baie d'Agadir et sa promenade balnéaire",
            "highlights": ["Plage de sable", "Promenade", "Golf & sud"],
            "bref_labels": ("Distance", "Format", "Idéal pour", "Meilleure période"),
        },
        "en": {
            "bref": {
                "distance": "~3 h from Marrakech",
                "format": "Day trip or 2–3 nights",
                "ideal": "Beach, rest, golf",
                "periode": "Year-round",
            },
            "quote": "A genuine seaside break — extend a Marrakech stay without flying elsewhere.",
            "mid_caption": "Agadir bay and its seaside promenade",
            "highlights": ["Sandy beach", "Promenade", "Golf & south"],
            "bref_labels": ("Distance", "Format", "Best for", "Best season"),
        },
    },
    "imlil": {
        "mid_img": "/assets/img/surmesure.jpg",
        "fr": {
            "bref": {
                "distance": "~1 h de Marrakech",
                "format": "Journée ou trek 2–3 jours",
                "ideal": "Randonnée, nature, villages",
                "periode": "Printemps & automne",
            },
            "quote": "Altitude, air frais, villages berbères — le Maroc n'est pas seulement désert et médinas.",
            "mid_caption": "Villages et terrasses autour d'Imlil, porte du Toubkal",
            "highlights": ["Toubkal", "Villages berbères", "Sentiers Atlas"],
            "bref_labels": ("Distance", "Format", "Idéal pour", "Meilleure période"),
        },
        "en": {
            "bref": {
                "distance": "~1 h from Marrakech",
                "format": "Day hike or 2–3 day trek",
                "ideal": "Hiking, nature, villages",
                "periode": "Spring & autumn",
            },
            "quote": "Altitude, cooler air, Berber villages — Morocco is more than desert and medinas.",
            "mid_caption": "Villages and terraces around Imlil, gateway to Toubkal",
            "highlights": ["Toubkal", "Berber villages", "Atlas trails"],
            "bref_labels": ("Distance", "Format", "Best for", "Best season"),
        },
    },
    "merzouga": {
        "mid_img": "/blog/assets/agafay-desert.jpg",
        "fr": {
            "bref": {
                "distance": "~8–9 h (ou vol)",
                "format": "2–3 jours",
                "ideal": "Sahara, bivouac, lever de soleil",
                "periode": "Octobre–avril",
            },
            "quote": "Des dunes de plus de 150 mètres — le paysage saharien le plus spectaculaire du Maroc.",
            "mid_caption": "Dunes de l'Erg Chebbi au lever du soleil",
            "highlights": ["Erg Chebbi", "Dromadaire & bivouac", "Lever de soleil"],
            "bref_labels": ("Distance", "Format", "Idéal pour", "Meilleure période"),
        },
        "en": {
            "bref": {
                "distance": "~8–9 h (or flight)",
                "format": "2–3 days",
                "ideal": "Sahara, camp, sunrise",
                "periode": "October–April",
            },
            "quote": "Dunes over 150 metres high — Morocco's most spectacular Saharan landscape.",
            "mid_caption": "Erg Chebbi dunes at sunrise",
            "highlights": ["Erg Chebbi", "Camel & camp", "Sunrise"],
            "bref_labels": ("Distance", "Format", "Best for", "Best season"),
        },
    },
    "cascades-ouzoud": {
        "mid_img": "/assets/img/desert.jpg",
        "fr": {
            "bref": {
                "distance": "~3 h de Marrakech",
                "format": "Journée",
                "ideal": "Cascades, nature, baignade",
                "periode": "Printemps & été",
            },
            "quote": "Environ 110 mètres de chute — l'une des plus hautes cascades d'Afrique du Nord.",
            "mid_caption": "Les cascades d'Ouzoud et leur gorge verdoyante",
            "highlights": ["Chutes 110 m", "Singes magots", "Baignade"],
            "bref_labels": ("Distance", "Format", "Idéal pour", "Meilleure période"),
        },
        "en": {
            "bref": {
                "distance": "~3 h from Marrakech",
                "format": "Day trip",
                "ideal": "Waterfalls, nature, swimming",
                "periode": "Spring & summer",
            },
            "quote": "About 110 metres of fall — among North Africa's tallest waterfalls.",
            "mid_caption": "Ouzoud Falls and their green gorge",
            "highlights": ["110 m falls", "Barbary macaques", "Swimming"],
            "bref_labels": ("Distance", "Format", "Best for", "Best season"),
        },
    },
    "souks-marrakech": {
        "mid_img": "/blog/assets/marrakech-authentique.jpg",
        "fr": {
            "bref": {
                "distance": "Médina de Marrakech",
                "format": "Demi-journée / journée",
                "ideal": "Artisanat, shopping, ateliers",
                "periode": "Toute l'année (matin)",
            },
            "quote": "Des corporations organisées par quartier — un héritage médiéval encore visible aujourd'hui.",
            "mid_caption": "Lanternes et artisanat dans les souks de Marrakech",
            "highlights": ["Tapis berbères", "Lanternes & cuivre", "Ateliers d'artisans"],
            "bref_labels": ("Distance", "Format", "Idéal pour", "Meilleure période"),
        },
        "en": {
            "bref": {
                "distance": "Marrakech medina",
                "format": "Half day / full day",
                "ideal": "Crafts, shopping, workshops",
                "periode": "Year-round (morning)",
            },
            "quote": "Guilds still organised by quarter — a medieval trade map you can still walk today.",
            "mid_caption": "Lanterns and crafts in the Marrakech souks",
            "highlights": ["Berber rugs", "Lanterns & copper", "Artisan workshops"],
            "bref_labels": ("Distance", "Format", "Best for", "Best season"),
        },
    },
}

HIGHLIGHT_ICONS = (
    # Simple line icons — same set rotated by index for visual variety
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l2.2 4.5L19 8.2l-3.5 3.4.8 4.9L12 14.2 7.7 16.5l.8-4.9L5 8.2l4.8-.7L12 3z" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12 8v4l2.5 1.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18V8.5L12 4l8 4.5V18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M9 18v-5h6v5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
)


DESTINATIONS = [
    {
        "slug": "essaouira",
        "img": "/assets/img/hero.jpg",
        "fr": {
            "title": "Essaouira depuis Marrakech — escapade océan | Coins Marocain",
            "desc": "Essaouira en une journée depuis Marrakech : remparts, port de pêche, médina UNESCO et vents atlantiques. Escapade océan privée.",
            "h1": "Essaouira, l'escapade océan depuis Marrakech",
            "cta": "Transport privé, départ de Marrakech",
            "internal": (
                '<p>Pour prolonger un <a href="/evenements">séjour événementiel</a> par une journée au bord de l\'eau, '
                'ou combiner avec une <a href="/carte">adresse de la carte</a> au retour — nous organisons le trajet privé.</p>'
            ),
            "sections": [
                (
                    "Un autre Maroc, à deux pas de Marrakech",
                    "À deux heures et demie de route de Marrakech, Essaouira offre un contraste total avec l'agitation de la médina. "
                    "Ici, pas de chaleur écrasante ni de ruelles labyrinthiques bondées : la ville se découvre au rythme du vent atlantique, "
                    "entre remparts fortifiés face à l'océan et façades chaulées de bleu et blanc qui lui valent parfois le surnom de "
                    "« Perle bleue de l'Atlantique ». Ancien comptoir portugais puis port stratégique du XVIIIe siècle, Essaouira a gardé "
                    "une identité maritime forte, encore visible dans son port de pêche animé dès l'aube et son marché aux poissons où "
                    "les prises du jour se négocient à voix haute.",
                ),
                (
                    "Que faire à Essaouira en une journée",
                    "La citadelle portugaise (Skala de la ville) offre l'une des plus belles vues sur l'océan et les remparts, canons d'époque "
                    "toujours en place. Le souk aux épices et bijoux berbères de la médina, classée au patrimoine mondial de l'UNESCO, se prête "
                    "bien à la flânerie et aux emplettes — moins pressant que celui de Marrakech, plus propice à prendre son temps. Pour le "
                    "déjeuner, le port reste une valeur sûre : poisson grillé du jour, servi dans les petits restaurants qui bordent les quais. "
                    "Les amateurs de sports nautiques apprécieront aussi la réputation d'Essaouira comme spot de référence pour le surf et le "
                    "kitesurf au Maroc, portée par des vents constants toute l'année.",
                ),
                (
                    "Comment organiser votre journée à Essaouira",
                    "Le trajet se fait généralement tôt le matin pour profiter d'une pleine journée sur place, retour à Marrakech en soirée. "
                    "C'est une bonne option pour rompre le rythme d'un séjour événementiel par une journée au bord de l'eau, sans les contraintes "
                    "d'un circuit de groupe standardisé.",
                ),
            ],
        },
        "en": {
            "title": "Essaouira day trip from Marrakech — Atlantic escape | Coins Marocain",
            "desc": "Private day trip to Essaouira from Marrakech: ramparts, fishing port, UNESCO medina and Atlantic breeze.",
            "h1": "Essaouira, an Atlantic day trip from Marrakech",
            "cta": "Private transfer from Marrakech",
            "internal": (
                '<p>Ideal after an <a href="/en/events">event stay</a>, or paired with a stop from our '
                '<a href="/en/map">map of places</a> on the way back.</p>'
            ),
            "sections": [
                (
                    "A different Morocco, a short drive away",
                    "About two and a half hours from Marrakech, Essaouira is a complete change of pace from the medina. "
                    "No crushing heat, no packed labyrinth: the town moves with the Atlantic wind, between ocean-facing ramparts "
                    "and blue-and-white façades that earned it the nickname “Blue Pearl of the Atlantic”. Once a Portuguese outpost "
                    "and later an 18th-century strategic port, Essaouira still feels maritime — from the dawn fishing harbour to the "
                    "lively fish market where the day's catch is bargained at full volume.",
                ),
                (
                    "What to do in Essaouira in a day",
                    "The Portuguese citadel (Skala) offers one of the finest views over the ocean and ramparts, with period cannons still in place. "
                    "The spice and Berber jewellery souk inside the UNESCO-listed medina is made for unhurried browsing — calmer than Marrakech. "
                    "Lunch at the port is a safe bet: grilled fish of the day in the small restaurants along the quays. Water-sports fans also know "
                    "Essaouira as a reference spot for surfing and kitesurfing in Morocco, thanks to steady winds year-round.",
                ),
                (
                    "How to plan your day",
                    "Most travellers leave early to enjoy a full day on site and return to Marrakech in the evening. "
                    "It is a clean way to break an event-focused stay with a day by the sea — without a standard group-tour script.",
                ),
            ],
        },
    },
    {
        "slug": "agadir",
        "img": "/assets/img/forfaits-hero.jpg",
        "fr": {
            "title": "Agadir depuis Marrakech — plage et modernité | Coins Marocain",
            "desc": "Escapade à Agadir depuis Marrakech : plage de sable, promenade balnéaire, golf et prolongement de séjour au sud.",
            "h1": "Agadir, plage et modernité au sud de Marrakech",
            "cta": "Journée balnéaire ou prolongement de séjour",
            "internal": (
                '<p>Complète bien un <a href="/evenements/team-building-retraites">séjour retraite ou team building</a> '
                'par une parenthèse reposante — ou une villa de la <a href="/carte">carte</a> côté Atlantique.</p>'
            ),
            "sections": [
                (
                    "Une ville reconstruite, tournée vers l'océan",
                    "À environ trois heures de route de Marrakech, Agadir change complètement de registre. Rasée par le séisme de 1960, "
                    "la ville a été entièrement reconstruite dans un style moderne et aéré, très différent du patrimoine ocre et labyrinthique "
                    "de Marrakech. Ici, on vient avant tout pour la plage : une immense étendue de sable fin qui s'étire sur plusieurs kilomètres, "
                    "bordée d'une promenade animée, de terrasses et d'hôtels balnéaires.",
                ),
                (
                    "Pour qui est faite cette escapade",
                    "Agadir séduit moins pour son patrimoine historique que pour sa capacité à offrir une vraie coupure balnéaire — utile pour "
                    "prolonger un séjour événementiel à Marrakech par quelques jours de détente en bord de mer, sans repartir loin. La ville dispose "
                    "aussi de plusieurs golfs réputés et sert de point de départ pour explorer le sud marocain (vallée du Souss, Taghazout pour le surf, "
                    "Paradise Valley). C'est une escapade qui complète bien un séjour orienté célébration ou retraite d'entreprise par une parenthèse plus reposante.",
                ),
                (
                    "Agadir en excursion ou en prolongement de séjour",
                    "Certains groupes choisissent d'y passer une seule journée pour changer d'air, d'autres préfèrent y ajouter deux ou trois nuits "
                    "en fin de séjour avant de reprendre l'avion — les deux formats se planifient facilement depuis Marrakech.",
                ),
            ],
        },
        "en": {
            "title": "Agadir from Marrakech — beach & modern coast | Coins Marocain",
            "desc": "Agadir from Marrakech: long sandy beach, seaside promenade, golf, and an easy southern extension to your stay.",
            "h1": "Agadir, beach and modern coast south of Marrakech",
            "cta": "Beach day or stay extension",
            "internal": (
                '<p>Pairs well after a <a href="/en/events/team-building-retreats">retreat or team-building</a> stay, '
                'or with a coastal address from our <a href="/en/map">map</a>.</p>'
            ),
            "sections": [
                (
                    "A rebuilt city facing the ocean",
                    "About three hours from Marrakech, Agadir changes the register entirely. Flattened by the 1960 earthquake, "
                    "the city was rebuilt in a modern, open style — far from Marrakech's ochre labyrinth. People come first for the beach: "
                    "a vast stretch of fine sand running for kilometres, lined with a lively promenade, terraces and seaside hotels.",
                ),
                (
                    "Who this escape is for",
                    "Agadir wins less on historic fabric than on a genuine seaside break — useful to extend an event stay in Marrakech "
                    "with a few calmer days by the sea without flying elsewhere. The city also has well-known golf courses and is a base "
                    "for the southern routes (Souss valley, Taghazout for surfing, Paradise Valley). It complements a celebration or corporate "
                    "retreat with a more restful parenthesis.",
                ),
                (
                    "Day trip or stay extension",
                    "Some groups come for a single day for a change of air; others add two or three nights at the end of the trip before flying home. "
                    "Both formats are easy to plan from Marrakech.",
                ),
            ],
        },
    },
    {
        "slug": "imlil",
        "img": "/blog/assets/ourika-vallee.jpg",
        "fr": {
            "title": "Imlil et Haut Atlas depuis Marrakech — randonnée | Coins Marocain",
            "desc": "Excursion à Imlil depuis Marrakech : randonnée dans le Haut Atlas, villages berbères, porte d'entrée du Toubkal.",
            "h1": "Imlil, randonnée dans le Haut Atlas",
            "cta": "Guide local et transfert privé",
            "internal": (
                '<p>Alternative montagne à la <a href="/activites/vallee-ourika">vallée de l\'Ourika</a> — '
                'ou étape nature dans un programme <a href="/evenements">événement / retraite</a>.</p>'
            ),
            "sections": [
                (
                    "La porte d'entrée du Haut Atlas",
                    "À seulement une heure de route de Marrakech, Imlil marque un changement de décor radical : altitude, air frais, "
                    "villages berbères accrochés aux flancs de montagne et vergers en terrasses qui rappellent que le Maroc n'est pas seulement "
                    "fait de désert et de médinas. Imlil est le point de départ classique pour l'ascension du mont Toubkal, plus haut sommet "
                    "d'Afrique du Nord (4167 m), mais le village se prête tout autant à des randonnées plus courtes, accessibles à tous les niveaux.",
                ),
                (
                    "Une immersion nature et culture berbère",
                    "Les sentiers autour d'Imlil traversent des hameaux berbères où le mode de vie a peu changé, entre agriculture en terrasses, "
                    "moulins traditionnels et hospitalité marquée — souvent l'occasion d'un thé à la menthe chez l'habitant en cours de route. "
                    "Le contraste avec la chaleur du désert ou l'effervescence de la médina en fait une escapade complémentaire pour qui veut "
                    "voir plusieurs visages du Maroc en un seul séjour.",
                ),
                (
                    "Une excursion à la journée ou un trek de plusieurs jours",
                    "Les groupes pressés font l'aller-retour dans la même journée avec une randonnée guidée de quelques heures ; ceux qui veulent "
                    "pousser plus loin dans le massif optent pour un trek de 2-3 jours avec nuits en gîte de montagne.",
                ),
            ],
        },
        "en": {
            "title": "Imlil & High Atlas from Marrakech — hiking | Coins Marocain",
            "desc": "Imlil day trip from Marrakech: High Atlas hiking, Berber villages, gateway to Mount Toubkal.",
            "h1": "Imlil, hiking in the High Atlas",
            "cta": "Local guide and private transfer",
            "internal": (
                '<p>A mountain alternative to the <a href="/activites/vallee-ourika">Ourika Valley</a> — '
                'or a nature day within an <a href="/en/events">events / retreat</a> programme.</p>'
            ),
            "sections": [
                (
                    "Gateway to the High Atlas",
                    "Only an hour from Marrakech, Imlil is a radical change of scenery: altitude, cooler air, Berber villages "
                    "clinging to the slopes and orchard terraces that remind you Morocco is more than desert and medinas. "
                    "Imlil is the classic start for climbing Mount Toubkal, North Africa's highest peak (4,167 m), but the village "
                    "also suits shorter hikes for every level.",
                ),
                (
                    "Nature and Berber culture",
                    "Trails around Imlil cross hamlets where daily life has changed little — terrace farming, traditional mills, "
                    "and warm hospitality, often including mint tea with a local family. The contrast with desert heat or medina energy "
                    "makes it a strong complement if you want several faces of Morocco in one stay.",
                ),
                (
                    "Day hike or multi-day trek",
                    "Busy groups do a same-day round trip with a few hours of guided walking; those who want to go deeper choose "
                    "a 2–3 day trek with nights in mountain lodges.",
                ),
            ],
        },
    },
    {
        "slug": "merzouga",
        "img": "/assets/img/desert.jpg",
        "fr": {
            "title": "Merzouga depuis Marrakech — nuit dans le Sahara | Coins Marocain",
            "desc": "Nuit à Merzouga et dunes de l'Erg Chebbi : dromadaire, bivouac berbère, lever de soleil. Escapade Sahara 2–3 jours.",
            "h1": "Merzouga, une nuit dans le grand désert du Sahara",
            "cta": "Bivouac et guide inclus",
            "internal": (
                '<p>Pour une version plus courte près de Marrakech, voir le <a href="/activites/desert-agafay">désert d\'Agafay</a> — '
                'ou le <a href="/blog/agafay-ou-ourika-comparatif">comparatif Agafay / Ourika</a>. '
                'Les formats multi-jours se planifient via nos <a href="/evenements">séjours événementiels</a> ou un <a href="/contact">devis</a>.</p>'
            ),
            "sections": [
                (
                    "Le vrai désert, au-delà d'Agafay",
                    "Agafay, à moins d'une heure de Marrakech, offre une expérience désert accessible et condensée en une soirée ou une nuit. "
                    "Merzouga, c'est une tout autre échelle : les dunes de l'Erg Chebbi, certaines dépassant 150 mètres de hauteur, forment "
                    "le paysage saharien le plus spectaculaire du Maroc. Ici, pas de raccourci possible — le dépaysement se mérite, "
                    "mais la récompense est à la hauteur du trajet.",
                ),
                (
                    "Ce que vous vivez à Merzouga",
                    "Le programme classique inclut une arrivée en fin de journée pour un coucher de soleil sur les dunes, un trajet à dos de "
                    "dromadaire jusqu'au bivouac, une nuit sous tente traditionnelle berbère avec musique gnaoua autour du feu, puis un lever "
                    "de soleil sur l'Erg Chebbi le lendemain matin — un des moments les plus photographiés du Maroc, et pour cause.",
                ),
                (
                    "Un trajet qui fait partie du voyage",
                    "Comptez environ 8 à 9 heures de route depuis Marrakech via le col du Tichka et la vallée du Drâa — un itinéraire "
                    "spectaculaire en lui-même, ou un vol court vers Errachidia/Ouarzazate pour réduire le temps de transport. "
                    "Ce format se vit sur 2 à 3 jours plutôt qu'à la journée, étapes intermédiaires et bivouac compris.",
                ),
            ],
        },
        "en": {
            "title": "Merzouga from Marrakech — Sahara overnight | Coins Marocain",
            "desc": "Merzouga and Erg Chebbi dunes: camel trek, Berber camp, sunrise. 2–3 day Sahara escape from Marrakech.",
            "h1": "Merzouga, a night in the great Sahara desert",
            "cta": "Camp stay and guide included",
            "internal": (
                '<p>For a shorter desert near Marrakech, see the <a href="/activites/desert-agafay">Agafay Desert</a>. '
                'Multi-day formats can be planned via <a href="/en/events">events stays</a> or a <a href="/en/contact">quote</a>.</p>'
            ),
            "sections": [
                (
                    "The real desert, beyond Agafay",
                    "Agafay, under an hour from Marrakech, offers an accessible desert evening or overnight. Merzouga is another scale: "
                    "the Erg Chebbi dunes, some over 150 metres high, form Morocco's most spectacular Saharan landscape. "
                    "There is no shortcut — the journey earns the reward.",
                ),
                (
                    "What you experience in Merzouga",
                    "The classic programme: late-day arrival for sunset on the dunes, a camel ride to camp, a night in a traditional "
                    "Berber tent with Gnawa music around the fire, then sunrise over Erg Chebbi — one of Morocco's most photographed moments, for good reason.",
                ),
                (
                    "The journey is part of the trip",
                    "Allow about 8–9 hours by road from Marrakech via the Tichka pass and the Drâa valley — spectacular in itself — "
                    "or a short flight to Errachidia/Ouarzazate to cut transfer time. This format is lived over 2–3 days, not as a day trip, "
                    "with intermediate stops and the overnight camp.",
                ),
            ],
        },
    },
    {
        "slug": "cascades-ouzoud",
        "img": "/blog/assets/ourika-vallee.jpg",
        "fr": {
            "title": "Cascades d'Ouzoud depuis Marrakech | Coins Marocain",
            "desc": "Excursion aux cascades d'Ouzoud : plus grande chute d'eau du Maroc, singes magots, baignade. À ~3 h de Marrakech.",
            "h1": "Cascades d'Ouzoud, la plus grande chute d'eau du Maroc",
            "cta": "Journée nature avec guide",
            "internal": (
                '<p>Complément ou alternative à la <a href="/activites/vallee-ourika">vallée de l\'Ourika</a> — '
                'idéal dans un programme <a href="/evenements">événementiel</a> qui mixe ville et nature.</p>'
            ),
            "sections": [
                (
                    "Une nature spectaculaire à trois heures de Marrakech",
                    "Les cascades d'Ouzoud comptent parmi les plus hautes chutes d'eau d'Afrique du Nord, avec une dénivellation "
                    "d'environ 110 mètres en plusieurs paliers. Nichées dans une gorge verdoyante du Moyen Atlas, elles offrent un "
                    "contraste saisissant avec les paysages secs qui dominent autour de Marrakech — un vert profond, une eau qui "
                    "rafraîchit l'air ambiant, et une faune locale surprenante.",
                ),
                (
                    "Ce qui distingue Ouzoud de la vallée de l'Ourika",
                    "Si vous avez déjà exploré la vallée de l'Ourika, les cascades d'Ouzoud offrent une échelle différente : des chutes "
                    "plus hautes, des sentiers qui permettent de descendre jusqu'au bassin en contrebas, et surtout une colonie de "
                    "singes magots en liberté qui vit dans les gorges environnantes — un des rares endroits au Maroc où on peut les "
                    "observer d'aussi près dans leur habitat naturel. C'est une bonne alternative ou un complément pour ceux qui "
                    "cherchent une nature plus sauvage.",
                ),
                (
                    "Une journée entre marche et baignade",
                    "Comptez une matinée pour la descente vers les bassins et la baignade, un déjeuner traditionnel sur place, "
                    "puis la remontée en début d'après-midi pour être de retour à Marrakech en soirée.",
                ),
            ],
        },
        "en": {
            "title": "Ouzoud Waterfalls from Marrakech | Coins Marocain",
            "desc": "Day trip to Ouzoud Falls: Morocco's tallest waterfall, Barbary macaques, swimming. About 3 hours from Marrakech.",
            "h1": "Ouzoud Falls, Morocco's tallest waterfall",
            "cta": "Guided nature day",
            "internal": (
                '<p>A complement or alternative to the <a href="/activites/vallee-ourika">Ourika Valley</a> — '
                'strong in an <a href="/en/events">events</a> programme that mixes city and nature.</p>'
            ),
            "sections": [
                (
                    "Spectacular nature three hours from Marrakech",
                    "Ouzoud Falls rank among North Africa's tallest waterfalls, dropping about 110 metres in several tiers. "
                    "Set in a green Middle Atlas gorge, they contrast sharply with the dry landscapes around Marrakech — deep green, "
                    "cooler air from the spray, and surprising local wildlife.",
                ),
                (
                    "How Ouzoud differs from Ourika",
                    "If you already know the Ourika Valley, Ouzoud offers a different scale: taller falls, trails down to the pools below, "
                    "and a colony of free-roaming Barbary macaques in the surrounding gorges — one of the rare places in Morocco to see them "
                    "so close in their habitat. A good alternative or add-on for wilder nature.",
                ),
                (
                    "A day of walking and swimming",
                    "Plan a morning descent to the pools and a swim, a traditional lunch on site, then the climb back early afternoon "
                    "to reach Marrakech by evening.",
                ),
            ],
        },
    },
    {
        "slug": "souks-marrakech",
        "img": "/assets/img/partenaire.jpg",
        "fr": {
            "title": "Souks de Marrakech — shopping et artisanat | Coins Marocain",
            "desc": "Explorer les souks de Marrakech : tapis, lanternes, maroquinerie, épices. Shopping artisanat avec guide local.",
            "h1": "Les souks de Marrakech, shopping et artisanat",
            "cta": "Visite guidée des ateliers",
            "internal": (
                '<p>Complète la <a href="/activites/visite-medina-nuit">visite privée de la médina de nuit</a> — '
                'et les adresses shopping de la <a href="/carte">carte</a>.</p>'
            ),
            "sections": [
                (
                    "Un territoire à part dans la médina",
                    "Au-delà de la simple visite nocturne de la médina, les souks de Marrakech méritent une exploration à part entière "
                    "pour qui aime chiner et rapporter un vrai souvenir d'artisanat marocain. Le labyrinthe de ruelles couvertes qui "
                    "s'étend autour de la place Jemaa el-Fna regroupe des dizaines de corporations organisées par quartier — un héritage "
                    "de l'organisation médiévale des métiers, encore largement visible aujourd'hui.",
                ),
                (
                    "Ce qu'on y trouve",
                    "Tapis berbères aux motifs traditionnels du Haut Atlas ou du Moyen Atlas, lanternes en fer forgé et en cuivre martelé, "
                    "maroquinerie de cuir tanné dans les tanneries voisines, épices vendues en pyramides colorées, argenterie et bijoux berbères, "
                    "poteries de Tamegroute aux glaçures vertes caractéristiques — chaque quartier du souk a sa spécialité, et savoir où chercher "
                    "fait toute la différence entre une visite frustrante et une vraie trouvaille.",
                ),
                (
                    "L'intérêt d'un guide local",
                    "S'y perdre seul fait partie du charme, mais s'y perdre avec un guide local permet d'éviter les pièges à touristes les plus "
                    "évidents, de comprendre la valeur réelle des pièces avant de négocier, et d'accéder à des ateliers d'artisans que les "
                    "visiteurs de passage ne trouvent jamais seuls. Un axe complémentaire à la découverte nocturne déjà proposée, pour ceux "
                    "qui viennent à Marrakech autant pour ramener un souvenir que pour voir la ville.",
                ),
            ],
        },
        "en": {
            "title": "Marrakech souks — shopping & crafts | Coins Marocain",
            "desc": "Explore Marrakech souks: rugs, lanterns, leather, spices. Artisan shopping with a local guide.",
            "h1": "Marrakech souks, shopping and crafts",
            "cta": "Guided workshop visit",
            "internal": (
                '<p>Complements a <a href="/activites/visite-medina-nuit">private night medina tour</a> — '
                'and shopping stops on our <a href="/en/map">map</a>.</p>'
            ),
            "sections": [
                (
                    "A world of its own inside the medina",
                    "Beyond a night walk in the medina, Marrakech's souks deserve their own exploration if you want real Moroccan craft "
                    "to take home. The covered labyrinth around Jemaa el-Fna still groups dozens of guilds by quarter — a medieval "
                    "organisation of trades that remains visible today.",
                ),
                (
                    "What you will find",
                    "Berber rugs from the High or Middle Atlas, wrought-iron and hammered-copper lanterns, leather from nearby tanneries, "
                    "spices stacked in coloured pyramids, silver and Berber jewellery, Tamegroute pottery with its signature green glaze — "
                    "each quarter has a speciality, and knowing where to look separates a frustrating visit from a real find.",
                ),
                (
                    "Why a local guide helps",
                    "Getting lost alone is part of the charm; getting lost with a local guide helps you skip the obvious tourist traps, "
                    "understand real value before bargaining, and reach artisan workshops passers-by never find. A strong complement to "
                    "the night discovery we already offer — for travellers who come to Marrakech as much to bring something home as to see the city.",
                ),
            ],
        },
    },
]


def write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print("wrote", path.relative_to(ROOT))


def build_hub_fr() -> str:
    cards = {
        "medina": "".join(
            [
                card(
                    "/activites/visite-medina-nuit",
                    "/assets/img/hero.jpg",
                    "Médina de nuit",
                    "Visite privée guidée",
                ),
                card(
                    "/guide-marrakech/souks-marrakech",
                    "/assets/img/partenaire.jpg",
                    "Souks de Marrakech",
                    "Shopping et artisanat",
                    "Nouveau",
                ),
                card(
                    "/blog/marrakech-authentique-activites-locales",
                    "/assets/img/partenaire.jpg",
                    "Marrakech authentique",
                    "Pourquoi choisir le local",
                ),
            ]
        ),
        "environs": "".join(
            [
                card(
                    "/guide-marrakech/essaouira",
                    "/assets/img/hero.jpg",
                    "Essaouira",
                    "Escapade océan à la journée",
                    "Nouveau",
                ),
                card(
                    "/guide-marrakech/agadir",
                    "/assets/img/forfaits-hero.jpg",
                    "Agadir",
                    "Plage et modernité au sud",
                    "Nouveau",
                ),
                card(
                    "/guide-marrakech/cascades-ouzoud",
                    "/blog/assets/ourika-vallee.jpg",
                    "Cascades d'Ouzoud",
                    "La plus grande chute d'eau du Maroc",
                    "Nouveau",
                ),
            ]
        ),
        "desert": "".join(
            [
                card(
                    "/activites/desert-agafay",
                    "/blog/assets/agafay-desert.jpg",
                    "Désert d'Agafay",
                    "Sunset, chameau, dîner privé",
                ),
                card(
                    "/guide-marrakech/merzouga",
                    "/assets/img/desert.jpg",
                    "Merzouga",
                    "Nuit dans le grand désert",
                    "Nouveau",
                ),
                card(
                    "/blog/agafay-ou-ourika-comparatif",
                    "/blog/assets/agafay-desert.jpg",
                    "Agafay ou Ourika ?",
                    "Lire le comparatif",
                ),
            ]
        ),
        "montagne": "".join(
            [
                card(
                    "/guide-marrakech/imlil",
                    "/blog/assets/ourika-vallee.jpg",
                    "Imlil",
                    "Randonnée dans l'Atlas",
                    "Nouveau",
                ),
                card(
                    "/activites/vallee-ourika",
                    "/blog/assets/ourika-vallee.jpg",
                    "Vallée de l'Ourika",
                    "Cascades &amp; villages berbères",
                ),
            ]
        ),
        "activites": "".join(
            [
                card(
                    "/activites/cours-cuisine-marocaine",
                    "/assets/img/partenaire.jpg",
                    "Cours de cuisine",
                    "Atelier avec chef local",
                ),
                card(
                    "/activites/hammam-traditionnel",
                    "/assets/img/journee-piscine/massage.jpg",
                    "Hammam traditionnel",
                    "Gommage &amp; détente",
                ),
                card(
                    "/carte/bien-etre",
                    "/assets/img/couple.jpg",
                    "Spas &amp; instituts",
                    "Sélection bien-être",
                ),
            ]
        ),
    }

    def panel(pid: str, label: str, grid: str, hidden: bool = True) -> str:
        h = " hidden" if hidden else ""
        return f"""      <div class="cm-esc-panel" role="tabpanel" id="panel-{pid}" aria-labelledby="tab-{pid}"{h}>
        <div class="cm-esc-grid">
{grid}        </div>
      </div>
"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
{HEAD_COMMON}  <title>Idées d'escapades autour de Marrakech | Coins Marocain</title>
  <meta name="description" content="Des idées pour explorer Marrakech et ses environs : médina, désert, Atlas, Essaouira, Merzouga, Ouzoud. Guide d'escapades Coins Marocain.">
  <link rel="canonical" href="https://coinsmarocain.com/guide-marrakech">
  <link rel="alternate" hreflang="fr" href="https://coinsmarocain.com/guide-marrakech">
  <link rel="alternate" hreflang="en" href="https://coinsmarocain.com/en/guide-marrakech">
  <link rel="alternate" hreflang="x-default" href="https://coinsmarocain.com/guide-marrakech">
  <meta property="og:title" content="Idées d'escapades autour de Marrakech">
  <meta property="og:description" content="Médina, désert, Atlas, océan : explorez Marrakech et ses environs avec notre guide d'escapades.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://coinsmarocain.com/guide-marrakech">
  <meta property="og:image" content="https://coinsmarocain.com/assets/img/hero.jpg">
</head>
<body class="cm-esc-page" data-wa-msg="Bonjour Yasmine, je souhaite des idées d'escapades autour de Marrakech.">
{header("fr", "/guide-marrakech", "/en/guide-marrakech")}<main>
  <!-- TEMP: image IA à remplacer -->
  <section class="cm-esc-hero">
    <div class="wrap">
      <p class="eyebrow">Guide · Marrakech &amp; environs</p>
      <h1>Des idées pour explorer Marrakech et ses environs</h1>
      <p class="lead">Médina, désert, montagne, océan : des escapades à lier à votre séjour — privées, sans circuit bas de gamme.</p>
    </div>
    <span class="cm-esc-ai-credit">Visuel d’inspiration</span>
  </section>
  <section class="cm-esc-mission" aria-label="Notre sélection">
    <div class="wrap">
      <p class="cm-esc-mission-kicker">Notre sélection</p>
      <p class="cm-esc-mission-text">Ce guide n'est pas une liste exhaustive — c'est notre sélection, celle qu'on partagerait avec un ami qui débarque à Marrakech. Chaque lieu est choisi parce qu'on y a mis les pieds, parce qu'on travaille avec ceux qui le font vivre, ou parce qu'il complète naturellement un séjour organisé avec nous. Pas de classement générique copié d'un site à l'autre : juste ce qu'on connaît, ce qu'on recommande, et ce qu'on peut organiser pour vous si l'envie vous prend.</p>
    </div>
  </section>
  <section class="cm-esc-tabs-wrap">
    <div class="wrap" data-esc-tabs>
      <div class="cm-esc-tabs" role="tablist" aria-label="Catégories d'escapades">
        <button type="button" class="cm-esc-tab" role="tab" id="tab-medina" aria-controls="panel-medina" aria-selected="true">Médina</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-environs" aria-controls="panel-environs" aria-selected="false" tabindex="-1">Environs</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-desert" aria-controls="panel-desert" aria-selected="false" tabindex="-1">Désert</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-montagne" aria-controls="panel-montagne" aria-selected="false" tabindex="-1">Montagne</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-activites" aria-controls="panel-activites" aria-selected="false" tabindex="-1">Activités</button>
      </div>
{panel("medina", "Médina", cards["medina"], False)}{panel("environs", "Environs", cards["environs"])}{panel("desert", "Désert", cards["desert"])}{panel("montagne", "Montagne", cards["montagne"])}{panel("activites", "Activités", cards["activites"])}    </div>
  </section>
</main>
{FOOTER_FR}{SCRIPTS}  <script src="/assets/guide-escapades.js?v={ASSET_V}" defer></script>
</body>
</html>
"""


def build_hub_en() -> str:
    cards = {
        "medina": "".join(
            [
                card("/activites/visite-medina-nuit", "/assets/img/hero.jpg", "Medina by night", "Private guided visit"),
                card(
                    "/en/guide-marrakech/souks-marrakech",
                    "/assets/img/partenaire.jpg",
                    "Marrakech souks",
                    "Shopping and crafts",
                    "New",
                ),
                card(
                    "/blog/marrakech-authentique-activites-locales",
                    "/assets/img/partenaire.jpg",
                    "Authentic Marrakech",
                    "Why choose local",
                ),
            ]
        ),
        "environs": "".join(
            [
                card(
                    "/en/guide-marrakech/essaouira",
                    "/assets/img/hero.jpg",
                    "Essaouira",
                    "Atlantic day trip",
                    "New",
                ),
                card(
                    "/en/guide-marrakech/agadir",
                    "/assets/img/forfaits-hero.jpg",
                    "Agadir",
                    "Beach and modern coast",
                    "New",
                ),
                card(
                    "/en/guide-marrakech/cascades-ouzoud",
                    "/blog/assets/ourika-vallee.jpg",
                    "Ouzoud Falls",
                    "Morocco's tallest waterfall",
                    "New",
                ),
            ]
        ),
        "desert": "".join(
            [
                card(
                    "/activites/desert-agafay",
                    "/blog/assets/agafay-desert.jpg",
                    "Agafay Desert",
                    "Sunset, camel, private dinner",
                ),
                card(
                    "/en/guide-marrakech/merzouga",
                    "/assets/img/desert.jpg",
                    "Merzouga",
                    "A night in the great desert",
                    "New",
                ),
                card(
                    "/blog/agafay-ou-ourika-comparatif",
                    "/blog/assets/agafay-desert.jpg",
                    "Agafay or Ourika?",
                    "Read the comparison",
                ),
            ]
        ),
        "montagne": "".join(
            [
                card(
                    "/en/guide-marrakech/imlil",
                    "/blog/assets/ourika-vallee.jpg",
                    "Imlil",
                    "Hiking in the Atlas",
                    "New",
                ),
                card(
                    "/activites/vallee-ourika",
                    "/blog/assets/ourika-vallee.jpg",
                    "Ourika Valley",
                    "Falls &amp; Berber villages",
                ),
            ]
        ),
        "activites": "".join(
            [
                card(
                    "/activites/cours-cuisine-marocaine",
                    "/assets/img/partenaire.jpg",
                    "Cooking class",
                    "Workshop with a local chef",
                ),
                card(
                    "/activites/hammam-traditionnel",
                    "/assets/img/journee-piscine/massage.jpg",
                    "Traditional hammam",
                    "Scrub &amp; unwind",
                ),
                card("/en/map/wellness", "/assets/img/couple.jpg", "Spas &amp; institutes", "Wellness selection"),
            ]
        ),
    }

    def panel(pid: str, grid: str, hidden: bool = True) -> str:
        h = " hidden" if hidden else ""
        return f"""      <div class="cm-esc-panel" role="tabpanel" id="panel-{pid}" aria-labelledby="tab-{pid}"{h}>
        <div class="cm-esc-grid">
{grid}        </div>
      </div>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{HEAD_COMMON}  <title>Day-trip ideas around Marrakech | Coins Marocain</title>
  <meta name="description" content="Ideas to explore Marrakech and beyond: medina, desert, Atlas, Essaouira, Merzouga, Ouzoud. Coins Marocain day-trip guide.">
  <link rel="canonical" href="https://coinsmarocain.com/en/guide-marrakech">
  <link rel="alternate" hreflang="fr" href="https://coinsmarocain.com/guide-marrakech">
  <link rel="alternate" hreflang="en" href="https://coinsmarocain.com/en/guide-marrakech">
  <link rel="alternate" hreflang="x-default" href="https://coinsmarocain.com/guide-marrakech">
  <meta property="og:title" content="Day-trip ideas around Marrakech">
  <meta property="og:description" content="Medina, desert, mountains, ocean — explore Marrakech and its surroundings.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://coinsmarocain.com/en/guide-marrakech">
  <meta property="og:image" content="https://coinsmarocain.com/assets/img/hero.jpg">
</head>
<body class="cm-esc-page" data-wa-msg="Hello Yasmine, I would like day-trip ideas around Marrakech.">
{header("en", "/guide-marrakech", "/en/guide-marrakech")}<main>
  <!-- TEMP: image IA à remplacer -->
  <section class="cm-esc-hero">
    <div class="wrap">
      <p class="eyebrow">Guide · Marrakech &amp; beyond</p>
      <h1>Ideas to explore Marrakech and its surroundings</h1>
      <p class="lead">Medina, desert, mountains, ocean — private day trips to weave into your stay, without budget group tours.</p>
    </div>
    <span class="cm-esc-ai-credit">Inspiration visual</span>
  </section>
  <section class="cm-esc-mission" aria-label="Our selection">
    <div class="wrap">
      <p class="cm-esc-mission-kicker">Our selection</p>
      <p class="cm-esc-mission-text">This guide isn't an exhaustive list — it's our pick, the one we'd share with a friend landing in Marrakech. Each place is here because we've stood there ourselves, because we work with the people who bring it to life, or because it naturally completes a stay we organize with you. No generic ranking copied from one site to the next: just what we know, what we recommend, and what we can arrange for you if the mood takes you.</p>
    </div>
  </section>
  <section class="cm-esc-tabs-wrap">
    <div class="wrap" data-esc-tabs>
      <div class="cm-esc-tabs" role="tablist" aria-label="Day-trip categories">
        <button type="button" class="cm-esc-tab" role="tab" id="tab-medina" aria-controls="panel-medina" aria-selected="true">Medina</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-environs" aria-controls="panel-environs" aria-selected="false" tabindex="-1">Nearby</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-desert" aria-controls="panel-desert" aria-selected="false" tabindex="-1">Desert</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-montagne" aria-controls="panel-montagne" aria-selected="false" tabindex="-1">Mountain</button>
        <button type="button" class="cm-esc-tab" role="tab" id="tab-activites" aria-controls="panel-activites" aria-selected="false" tabindex="-1">Activities</button>
      </div>
{panel("medina", cards["medina"], False)}{panel("environs", cards["environs"])}{panel("desert", cards["desert"])}{panel("montagne", cards["montagne"])}{panel("activites", cards["activites"])}    </div>
  </section>
</main>
{FOOTER_EN}{SCRIPTS}  <script src="/assets/guide-escapades.js?v={ASSET_V}" defer></script>
</body>
</html>
"""


def _bref_html(meta_lang: dict, lang: str) -> str:
    b = meta_lang["bref"]
    dist, fmt, ideal, periode = meta_lang["bref_labels"]
    title = "En bref" if lang == "fr" else "At a glance"
    rows = (
        (dist, b["distance"]),
        (fmt, b["format"]),
        (ideal, b["ideal"]),
        (periode, b["periode"]),
    )
    lis = "\n".join(
        f'        <div class="cm-esc-bref-row"><dt>{lab}</dt><dd>{val}</dd></div>' for lab, val in rows
    )
    return f"""      <aside class="cm-esc-bref" aria-label="{title}">
        <p class="cm-esc-bref-title">{title}</p>
        <dl class="cm-esc-bref-list">
{lis}
        </dl>
      </aside>
"""


def _highlights_html(labels: list[str]) -> str:
    cards = []
    for i, lab in enumerate(labels[:3]):
        icon = HIGHLIGHT_ICONS[i % len(HIGHLIGHT_ICONS)]
        cards.append(
            f"""        <div class="cm-esc-hl">
          <span class="cm-esc-hl-icon">{icon}</span>
          <span class="cm-esc-hl-label">{lab}</span>
        </div>"""
        )
    return (
        '      <div class="cm-esc-highlights" aria-label="Highlights">\n'
        + "\n".join(cards)
        + "\n      </div>\n"
    )


def build_dest(d: dict, lang: str) -> str:
    slug = d["slug"]
    fr_path = f"/guide-marrakech/{slug}"
    en_path = f"/en/guide-marrakech/{slug}"
    path = fr_path if lang == "fr" else en_path
    content = d["fr"] if lang == "fr" else d["en"]
    meta = DEST_META[slug]
    meta_lang = meta[lang]
    sections = content["sections"]
    first_h2, first_p = sections[0]
    rest = sections[1:]

    lead = f"""      <div class="cm-esc-dest-lead">
        <h2>{first_h2}</h2>
        <p>{first_p}</p>
      </div>
{_bref_html(meta_lang, lang)}"""

    mid = f"""  <!-- TEMP: image IA à remplacer -->
  <figure class="cm-esc-mid">
    <div class="cm-esc-mid-media" style="background-image:url('{meta["mid_img"]}')"></div>
    <figcaption class="cm-esc-mid-cap">{meta_lang["mid_caption"]}</figcaption>
    <span class="cm-esc-ai-credit">{"Visuel d’inspiration" if lang == "fr" else "Inspiration visual"}</span>
  </figure>
"""

    quote = f"""      <blockquote class="cm-esc-quote">
        <p>{meta_lang["quote"]}</p>
      </blockquote>
"""

    rest_parts = []
    for i, (h2, p) in enumerate(rest):
        rest_parts.append(f"      <h2>{h2}</h2>\n      <p>{p}</p>")
        if i == 0:
            rest_parts.append(_highlights_html(meta_lang["highlights"]))

    guide_lbl = "Guide des escapades" if lang == "fr" else "Day-trip guide"
    guide_href = "/guide-marrakech" if lang == "fr" else "/en/guide-marrakech"
    home_lbl = "Accueil" if lang == "fr" else "Home"
    home_href = "/" if lang == "fr" else "/en/"
    caption = "Visuel d’inspiration" if lang == "fr" else "Inspiration visual"
    cta_html = cta(content["cta"]) if lang == "fr" else cta_en(content["cta"])
    footer = FOOTER_FR if lang == "fr" else FOOTER_EN
    og_locale = "fr_FR" if lang == "fr" else "en_GB"
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
{HEAD_COMMON}  <title>{content["title"]}</title>
  <meta name="description" content="{content["desc"]}">
  <link rel="canonical" href="https://coinsmarocain.com{path}">
  <link rel="alternate" hreflang="fr" href="https://coinsmarocain.com{fr_path}">
  <link rel="alternate" hreflang="en" href="https://coinsmarocain.com{en_path}">
  <link rel="alternate" hreflang="x-default" href="https://coinsmarocain.com{fr_path}">
  <meta property="og:title" content="{content["h1"]}">
  <meta property="og:description" content="{content["desc"]}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="https://coinsmarocain.com{path}">
  <meta property="og:image" content="https://coinsmarocain.com{d["img"]}">
  <meta property="og:locale" content="{og_locale}">
</head>
<body class="cm-esc-page" data-wa-msg="{content["h1"]}">
{header(lang, fr_path, en_path)}<main>
  <!-- TEMP: image IA à remplacer -->
  <section class="cm-esc-dest-hero" style="background-image:linear-gradient(180deg,rgba(30,24,18,.4),rgba(20,16,12,.78)),url('{d["img"]}')">
    <div class="wrap">
      <p class="cm-esc-crumb"><a href="{home_href}">{home_lbl}</a> · <a href="{guide_href}">{guide_lbl}</a></p>
      <h1>{content["h1"]}</h1>
    </div>
    <span class="cm-esc-ai-credit">{caption}</span>
  </section>
  <article class="cm-esc-dest-body">
    <div class="cm-esc-dest-intro">
{lead}    </div>
{mid}{quote}
{chr(10).join(rest_parts)}
      {content["internal"]}
  </article>
{cta_html}</main>
{footer}{SCRIPTS}</body>
</html>
"""


def main() -> None:
    write(ROOT / "guide-marrakech" / "index.html", build_hub_fr())
    write(ROOT / "en" / "guide-marrakech" / "index.html", build_hub_en())
    for d in DESTINATIONS:
        write(ROOT / "guide-marrakech" / f"{d['slug']}.html", build_dest(d, "fr"))
        write(ROOT / "en" / "guide-marrakech" / f"{d['slug']}.html", build_dest(d, "en"))


if __name__ == "__main__":
    main()
