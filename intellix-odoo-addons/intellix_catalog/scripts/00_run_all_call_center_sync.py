# -*- coding: utf-8 -*-
"""Alias — utilise le sync catalogue complet."""
assert "env" in dir(), "Exécuter via: odoo-bin shell -d intellixcrm"
exec(open("/odoo/custom/addons/intellix_catalog/scripts/00_run_all_intellix_catalog_sync.py").read())
