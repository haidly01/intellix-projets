# -*- coding: utf-8 -*-
"""Migration 19.0.2.12.0 — alertes + bridge Cursor POC."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
