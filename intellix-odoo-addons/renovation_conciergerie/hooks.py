# -*- coding: utf-8 -*-


def post_init_hook(env):
    env['account.account']._intellix_activate_outstanding_payment_accounts()
    tour = env.ref("doorway_onboarding.tour_renovation", raise_if_not_found=False)
    if tour:
        tour.sudo().write(
            {"home_action_xmlid": "renovation_conciergerie.doorway_action_pipeline_all"}
        )
        step = tour.step_ids.filtered(lambda s: s.key == "pipelines")[:1]
        if step:
            step.sudo().write(
                {
                    "action_xmlid": "renovation_conciergerie.doorway_action_pipeline_all",
                    "action_label": "Tous les pipelines",
                }
            )
