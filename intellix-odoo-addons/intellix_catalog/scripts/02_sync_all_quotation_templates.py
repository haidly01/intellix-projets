# -*- coding: utf-8 -*-
"""
Intellix — synchronisation TOUS les modèles de devis (idempotent).

Prérequis : 01_sync_all_products.py

Exécution SSH :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/lib_intellix_sync.py").read())
exec(open("/odoo/custom/addons/intellix_catalog/scripts/02_sync_all_quotation_templates.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"
assert "upsert_quotation_template" in dir(), "Charger lib_intellix_sync.py avant ce script"

# --- CALL CENTER ---
CALL_CENTER_TEMPLATES = [
    {
        "name": "Call Center — 10 agents",
        "sequence": 10,
        "group": "Call Center",
        "note": NOTE_LAUNCH_CC,
        "expected_total": 395.0,
        "lines": [
            ("INTLX-VOIP-CC-S", 1),
            ("INTLX-CC-SAAS", 10),
            ("INTLX-IA-M", 1),
            ("INTLX-SETUP-CC", 1),
        ],
    },
    {
        "name": "Call Center — 30 agents",
        "sequence": 20,
        "group": "Call Center",
        "note": NOTE_LAUNCH_CC,
        "expected_total": 1040.0,
        "lines": [
            ("INTLX-VOIP-CC-L", 1),
            ("INTLX-CC-SAAS", 30),
            ("INTLX-IA-L", 1),
            ("INTLX-SETUP-CC", 1),
        ],
    },
    {
        "name": "Call Center — 50 agents",
        "sequence": 30,
        "group": "Call Center",
        "note": NOTE_LAUNCH_CC,
        "expected_total": 1690.0,
        "lines": [
            ("INTLX-VOIP-CC-L", 1),
            ("INTLX-CC-SAAS", 50),
            ("INTLX-IA-XL", 1),
            ("INTLX-SETUP-CC", 1),
        ],
    },
]

# --- MARKETING ---
MARKETING_TEMPLATES = [
    {
        "name": "Marketing — Gestion Campagnes Starter",
        "sequence": 40,
        "group": "Marketing",
        "note": NOTE_LAUNCH_MKT,
        "expected_total": 170.0,
        "lines": [
            ("INTLX-MKT-S", 1),
            ("INTLX-CC-SAAS", 1),
        ],
    },
    {
        "name": "Marketing — Gestion Campagnes Scale",
        "sequence": 50,
        "group": "Marketing",
        "note": NOTE_LAUNCH_MKT,
        "expected_total": 420.0,
        "lines": [
            ("INTLX-MKT-L", 1),
            ("INTLX-CC-SAAS", 1),
        ],
    },
    {
        "name": "Marketing — Campagnes + Équipe (5 users)",
        "sequence": 55,
        "group": "Marketing",
        "note": NOTE_LAUNCH_MKT,
        "expected_total": 375.0,
        "lines": [
            ("INTLX-MKT-S", 1),
            ("INTLX-CC-SAAS", 5),
            ("INTLX-IA-M", 1),
        ],
    },
]

ALL_TEMPLATES = CALL_CENTER_TEMPLATES + MARKETING_TEMPLATES

print("=" * 60)
print("Intellix — sync TOUS les modèles de devis")
print(f"Validité : {VALIDITY_DAYS} jours")
print("=" * 60)

errors = []
warnings = []

for section, templates in [
    ("Call Center", CALL_CENTER_TEMPLATES),
    ("Marketing", MARKETING_TEMPLATES),
]:
    print(f"\n{'=' * 40}\n  {section}\n{'=' * 40}")
    for spec in templates:
        print(f"\n--- {spec['name']} ---")
        try:
            _tpl, total, total_ok = upsert_quotation_template(env, spec)
            if not total_ok:
                warnings.append(f"{spec['name']}: total {total:.2f}")
        except ValueError as exc:
            errors.append(str(exc))
            print(f"  ERREUR : {exc}")

print("\n--- Vérification ---")
ok = verify_templates(env, ALL_TEMPLATES)

if warnings:
    print("\nAvertissements totaux :")
    for w in warnings:
        print(f"  ! {w}")

if errors:
    print("\nÉchec — corrigez les erreurs avant commit.")
    env.cr.rollback()
elif not ok:
    print("\nÉchec — modèles incomplets.")
    env.cr.rollback()
else:
    env.cr.commit()
    print("\nCommit OK.")
