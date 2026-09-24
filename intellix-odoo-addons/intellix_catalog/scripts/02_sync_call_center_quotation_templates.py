# -*- coding: utf-8 -*-
"""Alias → 02_sync_all_quotation_templates.py (Call Center + Marketing)."""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"
exec(open("/odoo/custom/addons/intellix_catalog/scripts/lib_intellix_sync.py").read())
exec(open("/odoo/custom/addons/intellix_catalog/scripts/02_sync_all_quotation_templates.py").read())
