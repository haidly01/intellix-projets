# -*- coding: utf-8 -*-
"""
Intellix — synchronisation complète : produits + modèles de devis.

Exécution SSH en une commande :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm <<'PY'
exec(open("/odoo/custom/addons/intellix_catalog/scripts/00_run_all_intellix_catalog_sync.py").read())
PY
"""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"

SCRIPTS_DIR = "/odoo/custom/addons/intellix_catalog/scripts"

exec(open(f"{SCRIPTS_DIR}/lib_intellix_sync.py").read())

print(">>> Étape 1/2 : tous les produits")
exec(open(f"{SCRIPTS_DIR}/01_sync_all_products.py").read())

print("\n>>> Étape 2/2 : tous les modèles de devis")
exec(open(f"{SCRIPTS_DIR}/02_sync_all_quotation_templates.py").read())

print("\n>>> Catalogue Intellix synchronisé.")
