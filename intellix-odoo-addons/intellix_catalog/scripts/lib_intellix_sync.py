# -*- coding: utf-8 -*-
"""
Bibliothèque partagée — sync catalogue Intellix (odoo shell).

Chargée via :
  exec(open(".../lib_intellix_sync.py").read())
"""
from __future__ import annotations

VALIDITY_DAYS = 15

NOTE_LAUNCH_CC = """
<p><strong>Offre lancement —</strong> Onboarding offert +
10% crédits IA bonus premier achat</p>
<p><strong>Validité :</strong> 15 jours</p>
"""

NOTE_LAUNCH_MKT = """
<p><strong>Offre lancement —</strong> Audit campagnes offert (valeur 500€)</p>
<p>Budget média facturé séparément selon plateforme.</p>
<p><strong>Validité :</strong> 15 jours</p>
"""


def ensure_category(env, parent_name, child_name):
    Category = env["product.category"].sudo()
    parent = Category.search(
        [("name", "=", parent_name), ("parent_id", "=", False)],
        limit=1,
    )
    if not parent:
        parent = Category.create({"name": parent_name})
        print(f"  [cat] créée : {parent_name}")
    child = Category.search(
        [("name", "=", child_name), ("parent_id", "=", parent.id)],
        limit=1,
    )
    if not child:
        child = Category.create({"name": child_name, "parent_id": parent.id})
        print(f"  [cat] créée : {parent_name} / {child_name}")
    return child


def ensure_uom(env, name):
    Uom = env["uom.uom"].sudo()
    uom = Uom.search([("name", "=", name)], limit=1)
    if uom:
        return uom
    uom = Uom.create({"name": name, "relative_factor": 1.0})
    print(f"  [uom] créée : {name}")
    return uom


def build_description(data):
    desc = data.get("description") or ""
    if data.get("recurrence") == "monthly" and "Facturation mensuelle" not in desc:
        desc = f"{desc} Facturation mensuelle."
    return desc.strip()


def upsert_product(env, data):
    """Crée ou met à jour un product.template par default_code."""
    Product = env["product.template"].sudo()
    ref = data["ref"]
    existing = Product.search([("default_code", "=", ref)], limit=1)

    category_map = {
        "Call Center": ("Intellix", "Call Center"),
        "Crédits IA": ("Intellix", "Crédits IA"),
        "Marketing": ("Intellix", "Marketing"),
    }
    parent, child = category_map.get(data["category"], ("Intellix", data["category"]))
    categ = ensure_category(env, parent, child)

    vals = {
        "name": data["name"],
        "default_code": ref,
        "type": data.get("type", "service"),
        "list_price": data["price"],
        "sale_ok": True,
        "purchase_ok": False,
        "categ_id": categ.id,
        "description_sale": build_description(data),
    }
    if data.get("uom"):
        vals["uom_id"] = ensure_uom(env, data["uom"]).id

    if existing:
        existing.write(vals)
        action = "mis à jour"
        record = existing
    else:
        record = Product.create(vals)
        action = "créé"
    print(f"  [{action}] {ref} — {data['name']} ({data['price']:.2f})")
    return record


def get_product_by_ref(env, ref):
    Product = env["product.product"].sudo()
    product = Product.search([("default_code", "=", ref)], limit=1)
    if not product:
        tmpl = env["product.template"].sudo().search([("default_code", "=", ref)], limit=1)
        product = tmpl.product_variant_id if tmpl else Product.browse()
    if not product:
        raise ValueError(f"Produit introuvable : {ref}")
    return product


def upsert_quotation_template(env, spec, default_note=None):
    """Crée ou met à jour un sale.order.template par nom."""
    Template = env["sale.order.template"].sudo()
    TemplateLine = env["sale.order.template.line"].sudo()

    name = spec["name"]
    template = Template.search([("name", "=", name)], limit=1)
    note = spec.get("note") or default_note or NOTE_LAUNCH_CC
    vals = {
        "name": name,
        "sequence": spec.get("sequence", 10),
        "number_of_days": spec.get("validity_days", VALIDITY_DAYS),
        "note": note,
        "active": True,
    }
    if template:
        template.write(vals)
        template.sale_order_template_line_ids.unlink()
        action = "mis à jour"
    else:
        template = Template.create(vals)
        action = "créé"

    seq = 10
    total = 0.0
    for ref, qty in spec["lines"]:
        product = get_product_by_ref(env, ref)
        TemplateLine.create({
            "sale_order_template_id": template.id,
            "sequence": seq,
            "product_id": product.id,
            "product_uom_qty": qty,
        })
        subtotal = qty * product.list_price
        total += subtotal
        print(f"    {qty:>4} × {ref:18} @ {product.list_price:>8.2f} = {subtotal:>8.2f}")
        seq += 10

    expected = spec.get("expected_total")
    total_ok = expected is None or abs(total - expected) < 0.01
    flag = "OK" if total_ok else f"ATTENTION (attendu {expected:.2f})"
    print(
        f"  [{action}] {name} — validité {vals['number_of_days']}j — "
        f"total {total:.2f} [{flag}]"
    )
    return template, total, total_ok


def verify_products(env, refs):
    Product = env["product.template"].sudo()
    found = Product.search([("default_code", "in", refs)])
    missing = set(refs) - set(found.mapped("default_code"))
    print(f"  Attendus : {len(refs)} | Trouvés : {len(found)}")
    if missing:
        print(f"  MANQUANTS : {sorted(missing)}")
        return False
    for p in found.sorted(lambda r: r.default_code):
        print(f"    OK {p.default_code:18} {p.list_price:>8.2f}  {p.name[:55]}")
    return True


def verify_templates(env, specs):
    Template = env["sale.order.template"].sudo()
    all_ok = True
    for spec in specs:
        t = Template.search([("name", "=", spec["name"])], limit=1)
        if not t:
            print(f"  MANQUANT : {spec['name']}")
            all_ok = False
            continue
        ok_lines = len(t.sale_order_template_line_ids) == len(spec["lines"])
        ok_days = t.number_of_days == spec.get("validity_days", VALIDITY_DAYS)
        status = "OK" if ok_lines and ok_days else "INCOMPLET"
        if status != "OK":
            all_ok = False
        print(
            f"  [{status}] {t.name} | {len(t.sale_order_template_line_ids)} lignes | "
            f"validité {t.number_of_days}j"
        )
    return all_ok
