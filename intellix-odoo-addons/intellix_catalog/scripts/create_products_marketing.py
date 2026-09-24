# -*- coding: utf-8 -*-
"""
Script 1 — Créer / mettre à jour les produits Marketing Intellix.

Exécution SSH Hostinger :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/create_products_marketing.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"

Product = env["product.template"].sudo()
Category = env["product.category"].sudo()

MARKETING_PRODUCTS = [
    {
        "ref": "INTLX-MKT-S",
        "name": "Intellix — Gestion Campagnes Starter",
        "price": 150.0,
        "type": "service",
        "recurrence": "monthly",
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
        "description": (
            "Gestion complète campagnes publicitaires IA. Budget média client supérieur à "
            "1 000€/mois. Honoraire : 15% du budget média. Minimum facturable : 400€/mois. "
            "Inclus : campagnes Meta/Google/LinkedIn, optimisation IA continue, "
            "rapports hebdomadaires, créatifs Canva + HeyGen, analyse concurrentielle."
        ),
    },
]


def _ensure_category():
    parent = Category.search([("name", "=", "Intellix"), ("parent_id", "=", False)], limit=1)
    if not parent:
        parent = Category.create({"name": "Intellix"})
        print("  [cat] créée : Intellix")
    child = Category.search(
        [("name", "=", "Marketing"), ("parent_id", "=", parent.id)],
        limit=1,
    )
    if not child:
        child = Category.create({"name": "Marketing", "parent_id": parent.id})
        print("  [cat] créée : Intellix / Marketing")
    return child


def _description(data):
    desc = data["description"]
    if data.get("recurrence") == "monthly" and "Facturation mensuelle" not in desc:
        return f"{desc} Facturation mensuelle."
    return desc


def upsert_product(data):
    ref = data["ref"]
    existing = Product.search([("default_code", "=", ref)], limit=1)
    vals = {
        "name": data["name"],
        "default_code": ref,
        "type": data["type"],
        "list_price": data["price"],
        "sale_ok": True,
        "purchase_ok": False,
        "categ_id": _ensure_category().id,
        "description_sale": _description(data),
    }
    if existing:
        existing.write(vals)
        print(f"  [EXISTE → mis à jour] {ref} | {data['name']} | {data['price']:.2f} €")
        return existing
    created = Product.create(vals)
    print(f"  [CRÉÉ] {ref} | {data['name']} | {data['price']:.2f} €")
    return created


print("=" * 70)
print("Script 1 — Produits Marketing Intellix")
print("=" * 70)

for item in MARKETING_PRODUCTS:
    upsert_product(item)

print("\n--- Confirmation ---")
refs = [p["ref"] for p in MARKETING_PRODUCTS]
found = Product.search([("default_code", "in", refs)])
for p in found.sorted(lambda r: r.default_code):
    print(f"  ✓ {p.default_code:14} {p.list_price:>8.2f} €  {p.name}")

env.cr.commit()
print("\nCommit OK — 2 produits Marketing synchronisés.")
