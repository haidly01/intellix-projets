# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        """
        ALTER TABLE pe_celebration_log
        DROP CONSTRAINT IF EXISTS pe_celebration_log_employee_id_occasion_type_occasion_year_key
        """
    )
    cr.execute(
        """
        ALTER TABLE pe_celebration_log
        DROP CONSTRAINT IF EXISTS pe_celebration_log_celebration_unique_year
        """
    )
    cr.execute(
        """
        DROP INDEX IF EXISTS pe_celebration_log_celebration_unique_year
        """
    )
