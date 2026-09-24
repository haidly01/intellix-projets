# -*- coding: utf-8 -*-
"""
Script 3 — Vérification complète catalogue Intellix.

Exécution SSH Hostinger :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/verify_all.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"

Product = env["product.template"].sudo()
Template = env["sale.order.template"].sudo()

EXPECTED_PRODUCTS = {
    "INTLX-VOIP-CC-S": 70.0,
    "INTLX-VOIP-CC-L": 65.0,
    "INTLX-CC-SAAS": 20.0,
    "INTLX-SETUP-CC": 0.0,
    "INTLX-SETUP": 0.0,
    "INTLX-IA-S": 50.0,
    "INTLX-IA-M": 125.0,
    "INTLX-IA-L": 250.0,
    "INTLX-IA-XL": 500.0,
    "INTLX-MKT-S": 150.0,
    "INTLX-MKT-L": 400.0,
}

EXPECTED_TEMPLATES = {
    "Call Center — 10 agents": {
        "lines": 4,
        "total": 395.0,
        "days": 15,
    },
    "Call Center — 30 agents": {
        "lines": 4,
        "total": 915.0,
        "days": 15,
    },
    "Call Center — 50 agents": {
        "lines": 4,
        "total": 1565.0,
        "days": 15,
    },
    "Marketing Géré — Budget Starter": {
        "lines": 3,
        "total": 200.0,
        "days": 15,
    },
    "Marketing Géré — Budget Scale": {
        "lines": 3,
        "total": 525.0,
        "days": 15,
    },
    "Call Center 30 agents + Marketing Géré": {
        "lines": 5,
        "total": 1315.0,
        "days": 15,
    },
}


def _template_total(template):
    total = 0.0
    for line in template.sale_order_template_line_ids:
        total += line.product_uom_qty * line.product_id.list_price
    return total


print("=" * 90)
print("Script 3 — Vérification catalogue Intellix")
print("=" * 90)

# --- Produits ---
print("\n### PRODUITS (ref INTLX-*) ###\n")
print(f"{'Référence':<20} {'Prix':>10} {'Attendu':>10} {'Statut':<8} Nom")
print("-" * 90)

all_intlx = Product.search([("default_code", "=like", "INTLX-%")], order="default_code")
product_ok = 0
product_ko = 0

for ref, expected_price in sorted(EXPECTED_PRODUCTS.items()):
    p = Product.search([("default_code", "=", ref)], limit=1)
    if not p:
        print(f"{ref:<20} {'—':>10} {expected_price:>10.2f} {'MANQUANT':<8}")
        product_ko += 1
        continue
    ok = abs(p.list_price - expected_price) < 0.01
    status = "OK" if ok else "PRIX!"
    if ok:
        product_ok += 1
    else:
        product_ko += 1
    print(
        f"{ref:<20} {p.list_price:>10.2f} {expected_price:>10.2f} {status:<8} {p.name[:40]}"
    )

extra = all_intlx.filtered(lambda p: p.default_code not in EXPECTED_PRODUCTS)
for p in extra:
    print(f"{p.default_code:<20} {p.list_price:>10.2f} {'—':>10} {'EXTRA':<8} {p.name[:40]}")

print(f"\nRésumé produits : {product_ok} OK | {product_ko} problème(s) | {len(all_intlx)} total INTLX")

# --- Modèles de devis ---
print("\n### MODÈLES DE DEVIS ###\n")
print(f"{'Modèle':<42} {'Lignes':>6} {'Total':>10} {'Jours':>6} {'Sign.':>6} {'Statut':<8}")
print("-" * 90)

template_ok = 0
template_ko = 0

for name, spec in EXPECTED_TEMPLATES.items():
    t = Template.search([("name", "=", name)], limit=1)
    if not t:
        print(f"{name:<42} {'—':>6} {'—':>10} {'—':>6} {'—':>6} {'MANQUANT':<8}")
        template_ko += 1
        continue
    total = _template_total(t)
    n_lines = len(t.sale_order_template_line_ids)
    ok = (
        n_lines == spec["lines"]
        and abs(total - spec["total"]) < 0.01
        and t.number_of_days == spec["days"]
        and t.require_signature
    )
    status = "OK" if ok else "INCOMPLET"
    if ok:
        template_ok += 1
    else:
        template_ko += 1
    sign = "oui" if t.require_signature else "non"
    print(
        f"{name:<42} {n_lines:>6} {total:>10.2f} {t.number_of_days:>6} {sign:>6} {status:<8}"
    )
    for line in t.sale_order_template_line_ids.sorted("sequence"):
        code = line.product_id.default_code or "?"
        print(
            f"    └ {line.product_uom_qty:>4.0f} × {code:<18} "
            f"@ {line.product_id.list_price:>8.2f} €"
        )

all_templates = Template.search([("name", "ilike", "Call Center%")]) | Template.search(
    [("name", "ilike", "Marketing%")]
)
extra_tpl = all_templates.filtered(lambda t: t.name not in EXPECTED_TEMPLATES)
if extra_tpl:
    print("\nModèles supplémentaires (hors spec) :")
    for t in extra_tpl:
        print(f"  • {t.name} ({len(t.sale_order_template_line_ids)} lignes)")

print(f"\nRésumé devis : {template_ok} OK | {template_ko} problème(s)")

# --- Bilan ---
print("\n" + "=" * 90)
if product_ko == 0 and template_ko == 0:
    print("BILAN : ✓ Catalogue Intellix conforme à la spec.")
else:
    print(f"BILAN : ✗ {product_ko} produit(s) et {template_ko} devis à corriger.")
    print("Relancer : create_products_marketing.py puis create_quote_templates.py")
print("=" * 90)

# Lecture seule — pas de commit
env.cr.rollback()
