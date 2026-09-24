# -*- coding: utf-8 -*-
"""
Intellix — produits Marketing uniquement (raccourci idempotent).

Exécution SSH :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/lib_intellix_sync.py").read())
exec(open("/odoo/custom/addons/intellix_catalog/scripts/03_sync_marketing_products.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"
assert "upsert_product" in dir(), "Charger lib_intellix_sync.py avant ce script"

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

print("=" * 60)
print("Intellix — sync produits Marketing")
print("=" * 60)
for item in MARKETING_PRODUCTS:
    upsert_product(env, item)
print("\n--- Vérification ---")
if verify_products(env, [p["ref"] for p in MARKETING_PRODUCTS]):
    env.cr.commit()
    print("\nCommit OK.")
else:
    env.cr.rollback()
