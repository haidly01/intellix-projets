# -*- coding: utf-8 -*-
"""Constructeurs de blocs (snippets) Odoo Website à partir du plan IA.

Chaque fonction renvoie une chaîne HTML correspondant à une ``<section>`` qui
utilise les classes et attributs des snippets natifs Odoo (``s_cover``,
``s_features``, ``s_three_columns``, ``s_call_to_action``, ``s_comparisons``,
``s_contact_info``, ``s_quotes_carousel``, ``s_numbers``…). Les attributs
``data-snippet`` / ``data-name`` permettent à l'éditeur Website de reconnaître
les blocs et de les rendre éditables.

Tout est défensif : valeurs manquantes → valeurs par défaut. Le texte injecté
est échappé pour éviter de casser le QWeb/HTML.
"""
from html import escape

DEFAULT_IMAGE = "/web/image/website.s_cover_default_image"
CARD_IMAGES = [
    "/web/image/website.s_three_columns_default_image_1",
    "/web/image/website.s_three_columns_default_image_2",
    "/web/image/website.s_three_columns_default_image_3",
]
FEATURE_ICONS = ["fa-rocket", "fa-bolt", "fa-shield", "fa-star", "fa-cogs", "fa-line-chart"]


def _t(value, default=""):
    """Texte échappé, robuste aux None / non-str."""
    if value is None:
        return escape(default)
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return escape(value if value else default)


def _href(value, default="/contactus"):
    if not value or not isinstance(value, str):
        return escape(default)
    value = value.strip()
    # On n'autorise que des liens internes ou http(s) / mailto / tel.
    if value.startswith(("/", "http://", "https://", "mailto:", "tel:", "#")):
        return escape(value)
    return escape(default)


def _as_list(value):
    return value if isinstance(value, list) else []


def hero(section, palette=None):
    """Bloc d'en-tête (s_cover) avec titre, accroche et boutons."""
    palette = palette or {}
    primary = palette.get("primary") or "#1f2937"
    heading = _t(section.get("heading") or section.get("title"), "Votre projet commence ici")
    subtitle = _t(
        section.get("subtitle") or section.get("body"),
        "Décrivez votre offre en une ou deux phrases percutantes.",
    )
    btn_label = _t(section.get("button_label"), "Découvrir")
    btn_href = _href(section.get("button_href"), "#")
    cta2_label = _t(section.get("secondary_button_label"), "Nous contacter")
    overlay = escape(str(primary))
    return f"""
<section class="s_cover parallax s_parallax_is_fixed o_cc o_cc5 pt192 pb192" data-snippet="s_cover" data-name="Couverture" data-scroll-background-ratio="1">
    <span class="s_parallax_bg oe_img_bg" style="background-image: url('{DEFAULT_IMAGE}'); background-position: 50% 50%;"/>
    <div class="o_we_bg_filter" style="background-color: {overlay}; opacity: 0.55;"/>
    <div class="container s_allow_columns">
        <h1 class="display-3" style="text-align: center; color: #ffffff;">{heading}</h1>
        <p class="lead" style="text-align: center; color: #ffffff;">{subtitle}</p>
        <p style="text-align: center;">
            <a href="{btn_href}" class="btn btn-primary btn-lg mb-2 o_translate_inline">{btn_label}</a>
            <a href="/contactus" class="btn btn-outline-light btn-lg mb-2 o_translate_inline">{cta2_label}</a>
        </p>
    </div>
</section>"""


def text_block(section, palette=None):
    """Bloc de texte simple (s_text_block) — utilisé pour 'about'/intro."""
    heading = section.get("heading") or section.get("title")
    body = _t(section.get("body"), "Racontez votre histoire et ce qui vous rend unique.")
    head_html = f'<h2 class="h3-fs">{_t(heading)}</h2>' if heading else ""
    return f"""
<section class="s_text_block pt48 pb48 o_cc o_cc1" data-snippet="s_text_block" data-name="Texte">
    <div class="container s_allow_columns">
        {head_html}
        <p>{body}</p>
    </div>
</section>"""


def image_text(section, palette=None):
    """Bloc image + texte (s_image_text) pour la section 'about'."""
    heading = _t(section.get("heading") or section.get("title"), "À propos de nous")
    body = _t(section.get("body"), "Présentez votre mission, vos valeurs et votre expertise.")
    btn_label = section.get("button_label")
    btn = (
        f'<a href="{_href(section.get("button_href"))}" class="btn btn-primary mt-2">{_t(btn_label)}</a>'
        if btn_label
        else ""
    )
    return f"""
<section class="s_image_text pt56 pb56 o_cc o_cc1" data-snippet="s_image_text" data-name="Image - Texte">
    <div class="container">
        <div class="row align-items-center">
            <div class="col-lg-6">
                <img class="img img-fluid rounded mx-auto" src="{DEFAULT_IMAGE}" alt=""/>
            </div>
            <div class="col-lg-6 pt24 pt-lg-0">
                <h2>{heading}</h2>
                <p class="lead">{body}</p>
                {btn}
            </div>
        </div>
    </div>
</section>"""


def features(section, palette=None):
    """Bloc 'Features' (s_features) : liste d'avantages avec icônes."""
    heading = _t(section.get("heading") or section.get("title"), "Ce que nous offrons")
    subtitle = _t(section.get("subtitle"), "Les points forts de notre solution.")
    items = _as_list(section.get("items"))[:6]
    if not items:
        items = [
            {"title": "Fiabilité", "text": "Une performance constante et une disponibilité maximale."},
            {"title": "Performance", "text": "Rapidité et efficacité pour des résultats concrets."},
            {"title": "Évolutivité", "text": "Une solution qui grandit avec votre activité."},
        ]
    cols = ""
    for idx, item in enumerate(items):
        icon = FEATURE_ICONS[idx % len(FEATURE_ICONS)]
        cols += f"""
            <div class="col-lg-4">
                <div class="s_hr pt-4 pb32"><hr class="w-100 mx-auto"/></div>
                <i class="s_features_icon fa {icon} mb-3 rounded bg-o-color-3" role="img"/>
                <div class="overflow-hidden">
                    <h3 class="h5-fs">{_t(item.get('title'), 'Atout')}</h3>
                    <p>{_t(item.get('text') or item.get('body'), '')}</p>
                </div>
            </div>"""
    return f"""
<section class="s_features pt64 pb64 o_cc o_cc1" data-snippet="s_features" data-name="Caractéristiques">
    <div class="container">
        <h2 class="h3-fs">{heading}</h2>
        <p class="lead">{subtitle}</p>
        <div class="row">{cols}
        </div>
    </div>
</section>"""


def cards(section, palette=None):
    """Bloc 3 colonnes en cartes (s_three_columns) pour services/offres."""
    heading = section.get("heading") or section.get("title")
    head_html = (
        f'<div class="mb-4"><h2 class="h3-fs">{_t(heading)}</h2>'
        f'<p class="lead">{_t(section.get("subtitle"), "")}</p></div>'
        if heading
        else ""
    )
    items = _as_list(section.get("items"))[:3]
    if not items:
        items = [
            {"title": "Service 1", "text": "Décrivez ce service en quelques mots."},
            {"title": "Service 2", "text": "Décrivez ce service en quelques mots."},
            {"title": "Service 3", "text": "Décrivez ce service en quelques mots."},
        ]
    cols = ""
    for idx, item in enumerate(items):
        img = CARD_IMAGES[idx % len(CARD_IMAGES)]
        cols += f"""
            <div data-name="Carte" class="col-lg-4 pt16 pb16">
                <div class="s_card o_card_img_top card h-100 o_cc o_cc1 my-0" data-snippet="s_card" data-name="Carte">
                    <figure class="o_card_img_wrapper ratio ratio-16x9 mb-0">
                        <img class="o_card_img card-img-top" src="{img}" alt=""/>
                    </figure>
                    <div class="card-body">
                        <h3 class="card-title h5-fs">{_t(item.get('title'), 'Service')}</h3>
                        <p class="card-text">{_t(item.get('text') or item.get('body'), '')}</p>
                    </div>
                </div>
            </div>"""
    return f"""
<section class="s_three_columns o_cc o_cc2 pt48 pb48" data-snippet="s_three_columns" data-name="Colonnes">
    <div class="container">
        {head_html}
        <div class="row d-flex align-items-stretch">{cols}
        </div>
    </div>
</section>"""


def numbers(section, palette=None):
    """Bloc de chiffres clés (s_numbers)."""
    heading = _t(section.get("heading") or section.get("title"), "En chiffres")
    items = _as_list(section.get("items"))[:4]
    if not items:
        items = [
            {"title": "+250", "text": "Clients satisfaits"},
            {"title": "98%", "text": "Taux de satisfaction"},
            {"title": "+10", "text": "Années d'expérience"},
        ]
    cols = ""
    width = 12 // max(len(items), 1)
    for item in items:
        cols += f"""
            <div class="col-md-{width}">
                <div class="text-center">
                    <span class="display-3 fw-bold">{_t(item.get('title') or item.get('value'), '0')}</span>
                    <p class="lead">{_t(item.get('text') or item.get('body'), '')}</p>
                </div>
            </div>"""
    return f"""
<section class="s_numbers o_cc o_cc2 pt56 pb56" data-snippet="s_numbers" data-name="Chiffres">
    <div class="container">
        <h2 class="h3-fs text-center mb-5">{heading}</h2>
        <div class="row">{cols}
        </div>
    </div>
</section>"""


def testimonials(section, palette=None):
    """Bloc témoignages (s_quotes_carousel simplifié en grille de citations)."""
    heading = _t(section.get("heading") or section.get("title"), "Ils nous font confiance")
    items = _as_list(section.get("items"))[:3]
    if not items:
        items = [
            {"quote": "Un accompagnement remarquable du début à la fin.", "author": "Client satisfait", "role": ""},
        ]
    cols = ""
    width = 12 // max(len(items), 1)
    for item in items:
        author = _t(item.get("author"), "Client")
        role = item.get("role")
        role_html = f'<small class="text-muted d-block">{_t(role)}</small>' if role else ""
        cols += f"""
            <div class="col-lg-{width}">
                <div class="s_card card o_cc o_cc1 h-100 p-3" data-snippet="s_card" data-name="Carte">
                    <blockquote class="blockquote mb-2"><p>“{_t(item.get('quote') or item.get('text'), '')}”</p></blockquote>
                    <footer class="blockquote-footer mt-auto">{author}{role_html}</footer>
                </div>
            </div>"""
    return f"""
<section class="s_quotes_carousel o_cc o_cc2 pt56 pb56" data-snippet="s_quotes_carousel" data-name="Témoignages">
    <div class="container">
        <h2 class="h3-fs text-center mb-5">{heading}</h2>
        <div class="row d-flex align-items-stretch gy-3">{cols}
        </div>
    </div>
</section>"""


def pricing(section, palette=None):
    """Bloc tarifs (s_comparisons) : plans en cartes."""
    heading = _t(section.get("heading") or section.get("title"), "Nos offres")
    subtitle = _t(section.get("subtitle"), "Des formules adaptées à vos besoins.")
    items = _as_list(section.get("items"))[:3]
    if not items:
        items = [
            {"name": "Essentiel", "price": "29€", "period": "/ mois", "features": ["Fonctionnalités de base"]},
            {"name": "Pro", "price": "59€", "period": "/ mois", "features": ["Tout l'Essentiel", "Support prioritaire"]},
            {"name": "Premium", "price": "99€", "period": "/ mois", "features": ["Tout le Pro", "Accompagnement dédié"]},
        ]
    cols = ""
    width = 12 // max(len(items), 1)
    for idx, item in enumerate(items):
        feats = _as_list(item.get("features"))
        feats_html = ""
        for feat in feats[:6]:
            feats_html += (
                '<li class="list-group-item px-0 bg-transparent text-reset">'
                '<i class="fa fa-check text-success" role="img"/>  '
                f"{_t(feat)}</li>"
            )
        btn_cls = "btn-primary" if idx == 1 else "btn-outline-primary"
        cols += f"""
            <div class="col-lg-{width}" data-name="Formule">
                <div class="s_card card o_cc o_cc1 h-100 my-0" data-snippet="s_card" data-name="Carte">
                    <div class="card-body">
                        <h3 class="card-title h5-fs">{_t(item.get('name') or item.get('title'), 'Formule')}</h3>
                        <div class="my-2">
                            <strong class="h2-fs">{_t(item.get('price'), '')}</strong>
                            <small class="text-muted">{_t(item.get('period'), '')}</small>
                        </div>
                        <p class="card-text small">{_t(item.get('description') or item.get('body'), '')}</p>
                        <a href="/contactus" class="btn {btn_cls} w-100 mb-3">{_t(item.get('button_label'), 'Choisir')}</a>
                        <ul class="list-group list-group-flush text-start">{feats_html}</ul>
                    </div>
                </div>
            </div>"""
    return f"""
<section class="s_comparisons pt56 pb56 o_cc o_cc1" data-snippet="s_comparisons" data-name="Tarifs">
    <div class="container">
        <div class="mb-4">
            <h2 class="h3-fs">{heading}</h2>
            <p class="lead">{subtitle}</p>
        </div>
        <div class="row gap-4 gap-lg-0">{cols}
        </div>
    </div>
</section>"""


def contact(section, palette=None):
    """Bloc coordonnées (s_contact_info)."""
    heading = _t(section.get("heading") or section.get("title"), "Contactez-nous")
    body = _t(
        section.get("body"),
        "Une question ? Notre équipe vous répond dans les plus brefs délais.",
    )
    email = _t(section.get("email"), "info@exemple.com")
    phone = _t(section.get("phone"), "+33 1 23 45 67 89")
    address = _t(section.get("address"), "1 rue de l'Exemple, 75000 Paris")
    return f"""
<section class="s_contact_info pt56 pb64 o_cc o_cc1" data-snippet="s_contact_info" data-name="Coordonnées">
    <div class="container">
        <div class="row align-items-center">
            <div class="col-lg-6">
                <h2>{heading}</h2>
                <p class="lead">{body}</p>
            </div>
            <div class="col-lg-6 pt24 pt-lg-0">
                <h3 class="h5-fs"><i class="fa fa-fw fa-envelope-o" role="presentation"/> Email</h3>
                <p><a href="mailto:{email}">{email}</a></p>
                <h3 class="h5-fs"><i class="fa fa-fw fa-phone" role="presentation"/> Téléphone</h3>
                <p><a href="tel:{phone}">{phone}</a></p>
                <h3 class="h5-fs"><i class="fa fa-fw fa-building-o" role="presentation"/> Adresse</h3>
                <p>{address}</p>
            </div>
        </div>
    </div>
</section>"""


def call_to_action(section, palette=None):
    """Bloc d'appel à l'action (s_call_to_action)."""
    heading = _t(section.get("heading") or section.get("title"), "Prêt à commencer ?")
    subtitle = _t(section.get("subtitle") or section.get("body"), "Parlons de votre projet dès aujourd'hui.")
    btn_label = _t(section.get("button_label"), "Nous contacter")
    btn_href = _href(section.get("button_href"), "/contactus")
    return f"""
<section class="s_call_to_action o_cc o_cc4 pt64 pb64" data-snippet="s_call_to_action" data-name="Appel à l'action">
    <div class="container">
        <div class="row align-items-center">
            <div class="col-lg-9">
                <h2 class="h3-fs">{heading}</h2>
                <p class="lead">{subtitle}</p>
            </div>
            <div class="col-lg-3">
                <p style="text-align: right;">
                    <a href="{btn_href}" class="btn btn-primary btn-lg">{btn_label}</a>
                </p>
            </div>
        </div>
    </div>
</section>"""


# Mapping type de section IA → fonction constructrice.
BUILDERS = {
    "hero": hero,
    "cover": hero,
    "banner": hero,
    "text": text_block,
    "intro": text_block,
    "about": image_text,
    "image_text": image_text,
    "story": image_text,
    "features": features,
    "benefits": features,
    "services": cards,
    "offer": cards,
    "cards": cards,
    "columns": cards,
    "numbers": numbers,
    "stats": numbers,
    "metrics": numbers,
    "testimonials": testimonials,
    "reviews": testimonials,
    "quotes": testimonials,
    "pricing": pricing,
    "plans": pricing,
    "contact": contact,
    "cta": call_to_action,
    "call_to_action": call_to_action,
}

# Type de repli si le type renvoyé par l'IA est inconnu.
FALLBACK_BUILDER = text_block


def build_section(section, palette=None):
    """Renvoie le HTML d'une section à partir de son dict (type + contenu).

    Robuste : type inconnu → bloc texte ; exception → chaîne vide.
    """
    if not isinstance(section, dict):
        return ""
    stype = (section.get("type") or "").strip().lower()
    builder = BUILDERS.get(stype, FALLBACK_BUILDER)
    try:
        return builder(section, palette=palette)
    except Exception:  # noqa: BLE001 — un bloc défaillant ne casse pas la page
        return ""


def build_sections(sections, palette=None):
    """Concatène le HTML de toutes les sections d'une page."""
    parts = [build_section(s, palette=palette) for s in _as_list(sections)]
    return "\n".join(p for p in parts if p)
