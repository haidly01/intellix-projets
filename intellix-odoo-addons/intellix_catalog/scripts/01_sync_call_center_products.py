# -*- coding: utf-8 -*-
"""Alias → 01_sync_all_products.py (Call Center + IA + Marketing)."""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"
exec(open("/odoo/custom/addons/intellix_catalog/scripts/lib_intellix_sync.py").read())
exec(open("/odoo/custom/addons/intellix_catalog/scripts/01_sync_all_products.py").read())
