# -*- coding: utf-8 -*-
{
    "name": "Doorway — SEO IA",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "summary": (
        "Assistant SEO assisté par IA (Claude) : audit & optimisation on-page "
        "du site Odoo, découverte d'opportunités de backlinks WHITE-HAT + "
        "génération d'emails d'approche, et gestion des citations / annuaires "
        "(SEO local QC + France). Aucune technique black-hat."
    ),
    "description": """
Doorway SEO IA
==============

Un assistant conversationnel (style « Léa ») dans le back-office, dans la même
philosophie que le Site Builder IA et l'Email Builder IA, qui couvre trois
capacités SEO :

1. OPTIMISATION ON-PAGE
   Audit de chaque page du site (``website.page``) : meta title / description,
   nombre de H1, hiérarchie des titres, couverture des attributs ``alt``, nombre
   de mots, usage du mot-clé cible, liens internes, données structurées JSON-LD,
   Open Graph. Score SEO par page + liste d'anomalies. Claude propose des meta
   optimisées, un jeu de mots-clés, des données structurées JSON-LD et des
   pistes d'amélioration. APPLY en un clic écrit dans les champs SEO natifs
   d'Odoo (``website_meta_*``), de façon idempotente.

2. OPPORTUNITÉS DE BACKLINKS — WHITE-HAT UNIQUEMENT
   À partir d'un brief (activité / niche / géo), Claude propose des CIBLES de
   backlinks réalistes et pertinentes (blogs sectoriels, partenaires, presse
   locale, pages ressources, annuaires pertinents) avec une approche suggérée
   et une justification. Génération d'emails d'approche (sujet + corps), créés
   comme ``mail.template`` (et ``doorway.message.template`` si présent).
   ⚠️ AUCUNE génération automatisée de liens, AUCUN spam de commentaires/forums,
   AUCUN PBN, AUCUN envoi automatique : uniquement de la prospection légitime.

3. CITATIONS / ANNUAIRES (SEO LOCAL)
   Une fiche NAP maîtresse (nom, adresse, téléphone, horaires, catégories, URL,
   description). Une liste d'annuaires pré-remplie et pertinente pour le Québec
   et la France. Claude génère un contenu de soumission cohérent (NAP) adapté à
   chaque annuaire. Suivi du statut de soumission par annuaire.

Module isolé. Ne modifie aucun autre module. Échoue proprement si la clé API
Claude est absente ou si la réponse JSON est invalide. Bright Data est
totalement optionnel (découverte SERP / vérification de citations) et dégrade
gracieusement s'il n'est pas configuré.
""",
    "author": "Doorway / IntelliX",
    "depends": [
        "base",
        "web",
        "mail",
        "website",
        "doorway_credits",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/seo_directory_data.xml",
        "data/seo_cron.xml",
        "views/seo_views.xml",
        "views/seo_portfolio_audit_views.xml",
        "views/seo_portfolio_dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_seo/static/src/css/seo.css",
            "doorway_seo/static/src/js/seo_dashboard.js",
            "doorway_seo/static/src/xml/seo_dashboard.xml",
            "doorway_seo/static/src/css/portfolio_dashboard.css",
            "doorway_seo/static/src/js/portfolio_dashboard.js",
            "doorway_seo/static/src/xml/portfolio_dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
