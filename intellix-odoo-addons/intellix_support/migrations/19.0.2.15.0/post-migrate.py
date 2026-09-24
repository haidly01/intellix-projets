# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        UPDATE intellix_support_ticket
        SET user_scope = CASE
            WHEN contact_user_id IS NOT NULL THEN 'specific'
            ELSE 'all'
        END
        WHERE user_scope IS NULL OR user_scope = ''
        """
    )
    cr.execute(
        """
        UPDATE intellix_support_ticket
        SET ticket_type = 'bug'
        WHERE ticket_type IS NULL OR ticket_type = ''
        """
    )
    _logger.info("intellix_support 19.0.2.15.0 — user_scope/ticket_type backfill done")
