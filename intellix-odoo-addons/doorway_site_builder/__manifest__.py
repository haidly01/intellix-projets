# -*- coding: utf-8 -*-
{
    "name": "Doorway — Site Builder IA",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "summary": (
        "Constructeur de site web assisté par IA (Claude) : un chat recueille "
        "le brief (inspiration, personas, objectifs, ton, secteur, pages) puis "
        "génère un plan de site et construit de vraies pages Odoo Website."
    ),
    "description": """
Doorway Site Builder IA
=======================

Un assistant conversationnel (style « Léa ») qui :

1. Recueille un brief client dans un chat back-office (inspiration / personas /
   objectifs / ton / secteur / pages souhaitées).
2. Appelle Claude (Anthropic) pour produire un PLAN DE SITE en JSON strict :
   structure des pages, sections ordonnées par page, copy générée, palette,
   ton, et SEO par page.
3. Génère de VRAIES pages Odoo Website (website.page + ir.ui.view QWeb) à partir
   de blocs (snippets) natifs Odoo, éditables dans l'éditeur Website.
4. Permet d'ITÉRER (« rends-le plus premium », « ajoute une page tarifs ») en
   réutilisant le plan précédent comme contexte : les pages sont mises à jour
   sans doublon (idempotent).

Aucune modification des autres modules. Échoue proprement si la clé API Claude
est absente ou si la réponse JSON est invalide.
""",
    "author": "Doorway / IntelliX",
    "depends": [
        "base",
        "web",
        "website",
        "doorway_credits",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/site_builder_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_site_builder/static/src/css/site_builder.css",
            "doorway_site_builder/static/src/js/website_builder_guard.js",
            "doorway_site_builder/static/src/js/site_builder.js",
            "doorway_site_builder/static/src/xml/site_builder.xml",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
