# -*- coding: utf-8 -*-
"""
Supprime les modèles de devis Intellix obsolètes (hors spec actuelle).

Exécution :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/cleanup_old_quote_templates.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"

Template = env["sale.order.template"].sudo()

OFFICIAL_NAMES = {
    "Call Center — 10 agents",
    "Call Center — 30 agents",
    "Call Center — 50 agents",
    "Marketing Géré — Budget Starter",
    "Marketing Géré — Budget Scale",
    "Call Center 30 agents + Marketing Géré",
}

# Anciens modèles intermédiaires à retirer
OBSOLETE_NAMES = [
    "Marketing — Gestion Campagnes Starter",
    "Marketing — Gestion Campagnes Scale",
    "Marketing — Campagnes + Équipe (5 users)",
]

print("=" * 70)
print("Nettoyage — modèles de devis obsolètes")
print("=" * 70)

removed = 0
for name in OBSOLETE_NAMES:
    templates = Template.search([("name", "=", name)])
    if not templates:
        print(f"  [—] Absent : {name}")
        continue
    for t in templates:
        n_lines = len(t.sale_order_template_line_ids)
        t.unlink()
        print(f"  [SUPPRIMÉ] {name} ({n_lines} ligne(s))")
        removed += 1

# Sécurité : tout modèle Intellix-like hors liste officielle
candidates = Template.search([
    "|", "|",
    ("name", "ilike", "Call Center%"),
    ("name", "ilike", "Marketing%"),
    ("name", "ilike", "Intellix%"),
])
extras = candidates.filtered(lambda t: t.name not in OFFICIAL_NAMES)
for t in extras:
    print(f"  [SUPPRIMÉ extra] {t.name}")
    t.unlink()
    removed += 1

if removed:
    env.cr.commit()
    print(f"\nCommit OK — {removed} modèle(s) supprimé(s).")
else:
    print("\nRien à supprimer — catalogue déjà propre.")
    env.cr.rollback()
