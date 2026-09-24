# -*- coding: utf-8 -*-
"""
Intellix — synchronisation TOUS les produits catalogue (idempotent).

Exécution SSH :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/lib_intellix_sync.py").read())
exec(open("/odoo/custom/addons/intellix_catalog/scripts/01_sync_all_products.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"
assert "upsert_product" in dir(), "Charger lib_intellix_sync.py avant ce script"

SCRIPTS_DIR = "/odoo/custom/addons/intellix_catalog/scripts"

CALL_CENTER_PRODUCTS = [
    {
        "ref": "INTLX-VOIP-CC-S",
        "name": "Intellix Call Center — VoIP Illimité Starter",
        "price": 70.0,
        "type": "service",
        "recurrence": "monthly",
        "category": "Call Center",
        "description": (
            "Appels illimités France, Espagne, Canada. Jusqu'à 10 agents. "
            "Numéros locaux, enregistrement, transfert intelligent inclus."
        ),
    },
    {
        "ref": "INTLX-VOIP-CC-L",
        "name": "Intellix Call Center — VoIP Illimité Scale",
        "price": 65.0,
        "type": "service",
        "recurrence": "monthly",
        "category": "Call Center",
        "description": (
            "Appels illimités France, Espagne, Canada. 11 agents et plus. "
            "Numéros locaux, enregistrement, transfert intelligent inclus."
        ),
    },
    {
        "ref": "INTLX-CC-SAAS",
        "name": "Intellix Call Center — SaaS Complet",
        "price": 20.0,
        "type": "service",
        "uom": "Utilisateur/Mois",
        "recurrence": "monthly",
        "category": "Call Center",
        "description": (
            "Accès complet tous modules Intellix. CRM IA, Agent vocal, Marketing, "
            "Traffic Manager, Gestion RH, Scrapper leads, Gamification, Coaching IA. "
            "Facturation mensuelle par utilisateur."
        ),
    },
    {
        "ref": "INTLX-SETUP-CC",
        "name": "Intellix — Onboarding Call Center",
        "price": 0.0,
        "type": "service",
        "category": "Call Center",
        "description": (
            "Configuration complète, import contacts, clonage voix Sofia, formation équipe, "
            "lancement première campagne. Offert au lancement."
        ),
    },
]

IA_PRODUCTS = [
    {
        "ref": "INTLX-IA-M",
        "name": "Intellix — Pack Crédits IA Medium",
        "price": 125.0,
        "type": "service",
        "recurrence": "monthly",
        "category": "Crédits IA",
        "description": (
            "Pack crédits IA mensuel — tier Medium. Agent vocal, coaching IA et "
            "automatisations pour équipes jusqu'à 10 agents."
        ),
    },
    {
        "ref": "INTLX-IA-L",
        "name": "Intellix — Pack Crédits IA Large",
        "price": 375.0,
        "type": "service",
        "recurrence": "monthly",
        "category": "Crédits IA",
        "description": (
            "Pack crédits IA mensuel — tier Large. Volume adapté aux centres "
            "d'appels de 30 agents."
        ),
    },
    {
        "ref": "INTLX-IA-XL",
        "name": "Intellix — Pack Crédits IA XL",
        "price": 625.0,
        "type": "service",
        "recurrence": "monthly",
        "category": "Crédits IA",
        "description": (
            "Pack crédits IA mensuel — tier XL. Volume entreprise pour 50 agents et plus."
        ),
    },
]

MARKETING_PRODUCTS = [
    {
        "ref": "INTLX-MKT-S",
        "name": "Intellix — Gestion Campagnes Starter",
        "price": 150.0,
        "type": "service",
        "recurrence": "monthly",
        "category": "Marketing",
        "description": (
            "Gestion complète campagnes publicitaires IA. Budget média client inférieur à "
            "1 000€/mois. Honoraire : 30% du budget média. Minimum facturable : 150€/mois. "
            "Inclus : création campagnes Meta/Google, optimisation IA continue, "
            "rapports hebdomadaires, créatifs Canva."
        ),
    },
    {
        "ref": "INTLX-MKT-L",
        "name": "Intellix — Gestion Campagnes Scale",
        "price": 400.0,
        "type": "service",
        "recurrence": "monthly",
        "category": "Marketing",
        "description": (
            "Gestion complète campagnes publicitaires IA. Budget média client supérieur à "
            "1 000€/mois. Honoraire : 15% du budget média. Minimum facturable : 400€/mois. "
            "Inclus : campagnes Meta/Google/LinkedIn, optimisation IA continue, "
            "rapports hebdomadaires, créatifs Canva + HeyGen, analyse concurrentielle."
        ),
    },
]

ALL_PRODUCTS = CALL_CENTER_PRODUCTS + IA_PRODUCTS + MARKETING_PRODUCTS

print("=" * 60)
print("Intellix — sync TOUS les produits")
print("=" * 60)

for section, items in [
    ("Call Center", CALL_CENTER_PRODUCTS),
    ("Crédits IA", IA_PRODUCTS),
    ("Marketing", MARKETING_PRODUCTS),
]:
    print(f"\n--- {section} ---")
    for item in items:
        upsert_product(env, item)

print("\n--- Vérification ---")
ok = verify_products(env, [p["ref"] for p in ALL_PRODUCTS])
if ok:
    env.cr.commit()
    print("\nCommit OK.")
else:
    env.cr.rollback()
    print("\nRollback — produits manquants.")
