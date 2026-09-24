# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    Prospect = env["doorway.callcenter.prospect"].sudo()
    Prospect._ensure_marketing_tags()
    _logger.info("Doorway call center prospecting: tags Marketing initialisés.")
