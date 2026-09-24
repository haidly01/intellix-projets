# -*- coding: utf-8 -*-
{
    "name": "Doorway — Email Builder IA",
    "version": "19.0.1.0.0",
    "category": "Marketing/Email Marketing",
    "summary": (
        "Constructeur d'emails assisté par IA (Claude) : un chat recueille le "
        "brief (objectif, persona, ton, offre, CTA) puis génère de vrais "
        "templates / campagnes email Odoo prêts à l'emploi."
    ),
    "description": """
Doorway Email Builder IA
========================

Un assistant conversationnel (style « Léa ») qui :

1. Recueille un brief client dans un chat back-office (objectif, persona cible,
   ton, offre / proposition de valeur, CTA, longueur de séquence, marque).
2. Appelle Claude (Anthropic) pour produire un email OU une courte séquence en
   JSON strict : objet(s) (1-2 variantes A/B), pré-en-tête, corps HTML
   responsive inliné, version texte de secours, et bouton(s) CTA.
3. Génère de VRAIS artefacts email Odoo, immédiatement utilisables :
   - ``mail.template`` (envoi transactionnel / depuis une fiche),
   - ``mailing.mailing`` (campagne d'emailing de masse, éditable),
   - ``doorway.message.template`` canal Email + ``doorway.message.campaign``
     (si le module doorway_messaging est installé) pour alimenter le flux de
     campagne multi-contacts existant.
4. Permet d'ITÉRER (« rends-le plus court », « plus premium », « ajoute une
   remise », « transforme en séquence de 3 emails ») en réutilisant le ou les
   emails précédents comme contexte : les artefacts sont mis à jour sans
   doublon (idempotent).

Aucune modification des autres modules. Échoue proprement si la clé API Claude
est absente ou si la réponse JSON est invalide.
""",
    "author": "Doorway / IntelliX",
    "depends": [
        "base",
        "web",
        "mail",
        "mass_mailing",
        "doorway_messaging",
        "doorway_credits",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/email_builder_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_email_builder/static/src/css/email_builder.css",
            "doorway_email_builder/static/src/js/email_builder.js",
            "doorway_email_builder/static/src/xml/email_builder.xml",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
