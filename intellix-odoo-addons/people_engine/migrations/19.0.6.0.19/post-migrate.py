# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute(
        """
        UPDATE pe_employee_profile
           SET variable_prime_customize = FALSE
         WHERE variable_prime_customize IS NULL
        """
    )
    cr.execute(
        """
        UPDATE pe_employment_contract
           SET variable_prime_customize = FALSE
         WHERE variable_prime_customize IS NULL
        """
    )

    template = env.ref(
        "people_engine.pe_prime_template_5pct_extra_revenue",
        raise_if_not_found=False,
    )
    if not template:
        return

    profiles = env["pe.employee.profile"].search(
        [
            ("type_remuneration", "=", "mixte"),
            ("variable_prime_template_id", "=", False),
            ("description_variable", "ilike", "5%"),
        ]
    )
    if profiles:
        profiles.write(
            {
                "variable_prime_template_id": template.id,
                "variable_prime_customize": False,
            }
        )

    zakaria = env["pe.employee.profile"].search(
        [("display_name", "ilike", "Zakaria Barmaki")], limit=1
    )
    if zakaria and not zakaria.variable_prime_template_id:
        zakaria.write(
            {
                "variable_prime_template_id": template.id,
                "variable_prime_customize": False,
            }
        )

    env["pe.employee.profile"].search(
        [
            ("type_remuneration", "=", "mixte"),
            ("variable_prime_template_id", "!=", False),
            ("variable_prime_customize", "=", False),
        ]
    )._apply_variable_prime_from_template()

    env["pe.employment.contract"].search(
        [
            ("type_remuneration", "=", "mixte"),
            ("variable_prime_template_id", "!=", False),
            ("variable_prime_customize", "=", False),
        ]
    )._apply_variable_prime_from_template()
