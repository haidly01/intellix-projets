# -*- coding: utf-8 -*-
"""
Script 2 — Créer / mettre à jour les 6 modèles de devis Intellix.

Prérequis : Script 1 (marketing) + produits catalogue Call Center / IA.

Exécution SSH Hostinger :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/create_quote_templates.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"

Template = env["sale.order.template"].sudo()
TemplateLine = env["sale.order.template.line"].sudo()
ProductTmpl = env["product.template"].sudo()
Product = env["product.product"].sudo()
Category = env["product.category"].sudo()
Uom = env["uom.uom"].sudo()

# --- Paramètres globaux ---
VALIDITY_DAYS = 15
REQUIRE_SIGNATURE = True
FOOTER = (
    "<p><em>Intellix — La suite IA pour centres "
    "d'appels performants | intellix.ai</em></p>"
)
GLOBAL_META = (
    "<p><small>Devise : EUR | Langue : Français | "
    "Conditions de paiement : 30 jours net | "
    f"Validité du devis : {VALIDITY_DAYS} jours</small></p>"
)

NOTE_CC_LAUNCH = (
    "<p><strong>Offre lancement —</strong> Onboarding offert + "
    "10% crédits IA bonus premier achat</p>"
)

NOTE_MKT_STARTER = (
    "<p>Honoraire = 30% du budget média réel. Minimum 150€/mois. "
    "Budget média facturé séparément en sus.</p>"
)

NOTE_MKT_SCALE = (
    "<p>Honoraire = 15% du budget média réel. Minimum 400€/mois. "
    "Budget média facturé séparément en sus.</p>"
)

NOTE_COMBO = (
    "<p><strong>Offre complète —</strong> Onboarding offert. "
    "Honoraire marketing = 15% du budget média en sus du forfait mensuel.</p>"
)

# Produits requis (prix catalogue pour les lignes de devis)
CATALOG_PRODUCTS = [
    {"ref": "INTLX-VOIP-CC-S", "name": "Intellix Call Center — VoIP Illimité Starter", "price": 70.0, "cat": "Call Center"},
    {"ref": "INTLX-VOIP-CC-L", "name": "Intellix Call Center — VoIP Illimité Scale", "price": 65.0, "cat": "Call Center"},
    {"ref": "INTLX-CC-SAAS", "name": "Intellix Call Center — SaaS Complet", "price": 20.0, "cat": "Call Center", "uom": "Utilisateur/Mois"},
    {"ref": "INTLX-SETUP-CC", "name": "Intellix — Onboarding Call Center", "price": 0.0, "cat": "Call Center"},
    {"ref": "INTLX-SETUP", "name": "Intellix — Onboarding", "price": 0.0, "cat": "Services"},
    {"ref": "INTLX-IA-S", "name": "Intellix — Pack Crédits IA Small", "price": 50.0, "cat": "Crédits IA"},
    {"ref": "INTLX-IA-M", "name": "Intellix — Pack Crédits IA Medium", "price": 125.0, "cat": "Crédits IA"},
    {"ref": "INTLX-IA-L", "name": "Intellix — Pack Crédits IA Large", "price": 250.0, "cat": "Crédits IA"},
    {"ref": "INTLX-IA-XL", "name": "Intellix — Pack Crédits IA XL", "price": 500.0, "cat": "Crédits IA"},
    {"ref": "INTLX-MKT-S", "name": "Intellix — Gestion Campagnes Starter", "price": 150.0, "cat": "Marketing"},
    {"ref": "INTLX-MKT-L", "name": "Intellix — Gestion Campagnes Scale", "price": 400.0, "cat": "Marketing"},
]

QUOTATION_TEMPLATES = [
    {
        "name": "Call Center — 10 agents",
        "sequence": 10,
        "description": None,
        "note_parts": [NOTE_CC_LAUNCH],
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
        "description": None,
        "note_parts": [NOTE_CC_LAUNCH],
        "expected_total": 915.0,
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
        "description": None,
        "note_parts": [NOTE_CC_LAUNCH],
        "expected_total": 1565.0,
        "lines": [
            ("INTLX-VOIP-CC-L", 1),
            ("INTLX-CC-SAAS", 50),
            ("INTLX-IA-XL", 1),
            ("INTLX-SETUP-CC", 1),
        ],
    },
    {
        "name": "Marketing Géré — Budget Starter",
        "sequence": 40,
        "description": "Client avec budget pub < 1 000€/mois",
        "note_parts": [NOTE_MKT_STARTER],
        "expected_total": 200.0,
        "lines": [
            ("INTLX-MKT-S", 1),
            ("INTLX-IA-S", 1),
            ("INTLX-SETUP", 1),
        ],
    },
    {
        "name": "Marketing Géré — Budget Scale",
        "sequence": 50,
        "description": "Client avec budget pub > 1 000€/mois",
        "note_parts": [NOTE_MKT_SCALE],
        "expected_total": 525.0,
        "lines": [
            ("INTLX-MKT-L", 1),
            ("INTLX-IA-M", 1),
            ("INTLX-SETUP", 1),
        ],
    },
    {
        "name": "Call Center 30 agents + Marketing Géré",
        "sequence": 60,
        "description": (
            "Offre complète centre d'appels avec gestion pub incluse"
        ),
        "note_parts": [NOTE_COMBO],
        "expected_total": 1315.0,
        "lines": [
            ("INTLX-VOIP-CC-L", 1),
            ("INTLX-CC-SAAS", 30),
            ("INTLX-IA-L", 1),
            ("INTLX-MKT-L", 1),
            ("INTLX-SETUP-CC", 1),
        ],
    },
]


def _ensure_category(parent_name, child_name):
    parent = Category.search([("name", "=", parent_name), ("parent_id", "=", False)], limit=1)
    if not parent:
        parent = Category.create({"name": parent_name})
    child = Category.search(
        [("name", "=", child_name), ("parent_id", "=", parent.id)],
        limit=1,
    )
    if not child:
        child = Category.create({"name": child_name, "parent_id": parent.id})
    return child


def _ensure_uom(name):
    uom = Uom.search([("name", "=", name)], limit=1)
    if not uom:
        uom = Uom.create({"name": name, "relative_factor": 1.0})
    return uom


def ensure_catalog_products():
    """Met à jour les prix catalogue requis par les modèles de devis."""
    print("\n--- Vérification produits catalogue ---")
    missing = []
    for data in CATALOG_PRODUCTS:
        ref = data["ref"]
        categ = _ensure_category("Intellix", data["cat"])
        vals = {
            "name": data["name"],
            "default_code": ref,
            "type": "service",
            "list_price": data["price"],
            "sale_ok": True,
            "purchase_ok": False,
            "categ_id": categ.id,
        }
        if data.get("uom"):
            vals["uom_id"] = _ensure_uom(data["uom"]).id
        existing = ProductTmpl.search([("default_code", "=", ref)], limit=1)
        if existing:
            existing.write(vals)
            print(f"  [OK] {ref} → {data['price']:.2f} €")
        else:
            ProductTmpl.create(vals)
            print(f"  [CRÉÉ] {ref} → {data['price']:.2f} €")
    return missing


def get_product(ref):
    product = Product.search([("default_code", "=", ref)], limit=1)
    if not product:
        tmpl = ProductTmpl.search([("default_code", "=", ref)], limit=1)
        product = tmpl.product_variant_id if tmpl else Product.browse()
    if not product:
        raise ValueError(f"Produit introuvable après sync : {ref}")
    return product


def build_note(spec):
    parts = []
    if spec.get("description"):
        parts.append(f"<p><em>{spec['description']}</em></p>")
    parts.extend(spec.get("note_parts") or [])
    parts.append(GLOBAL_META)
    parts.append(FOOTER)
    return "\n".join(parts)


def upsert_template(spec):
    name = spec["name"]
    existing = Template.search([("name", "=", name)], limit=1)
    note = build_note(spec)
    vals = {
        "name": name,
        "sequence": spec["sequence"],
        "number_of_days": VALIDITY_DAYS,
        "note": note,
        "require_signature": REQUIRE_SIGNATURE,
        "active": True,
    }
    if existing:
        existing.write(vals)
        existing.sale_order_template_line_ids.unlink()
        action = "EXISTE → mis à jour"
        template = existing
    else:
        template = Template.create(vals)
        action = "CRÉÉ"

    seq = 10
    total = 0.0
    for ref, qty in spec["lines"]:
        product = get_product(ref)
        TemplateLine.create({
            "sale_order_template_id": template.id,
            "sequence": seq,
            "product_id": product.id,
            "product_uom_qty": qty,
        })
        sub = qty * product.list_price
        total += sub
        print(f"      {qty:>4} × {ref:18} @ {product.list_price:>8.2f} € = {sub:>8.2f} €")
        seq += 10

    expected = spec.get("expected_total")
    ok = expected is None or abs(total - expected) < 0.01
    flag = "OK" if ok else f"ÉCART (attendu {expected:.2f} €)"
    print(f"  [{action}] {name}")
    print(f"      Total : {total:.2f} €/mois [{flag}] | Validité : {VALIDITY_DAYS}j | Signature : oui")
    return template, ok


print("=" * 70)
print("Script 2 — Modèles de devis Intellix (6 modèles)")
print("=" * 70)

ensure_catalog_products()

errors = []
print("\n--- Création / mise à jour des modèles ---")
for spec in QUOTATION_TEMPLATES:
    print(f"\n  ► {spec['name']}")
    try:
        _tpl, ok = upsert_template(spec)
        if not ok:
            errors.append(f"Total incorrect : {spec['name']}")
    except ValueError as exc:
        errors.append(str(exc))
        print(f"      ERREUR : {exc}")

if errors:
    print("\n--- ÉCHEC ---")
    for e in errors:
        print(f"  ✗ {e}")
    env.cr.rollback()
    print("Rollback effectué.")
else:
    env.cr.commit()
    print("\nCommit OK — 6 modèles de devis synchronisés.")
