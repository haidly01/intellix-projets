# -*- coding: utf-8 -*-

from odoo import fields

HIBA_LOGIN = "hiba@agencedoorway.com"
MARTIN_LOGIN = "martin@agencedoorway.com"
BASE_MAD = 5000.0


def _restrict_global_stages_from_coins_quebec(env):
    """Les étapes sans équipe (Nouveau / Qualifié Odoo) s'affichent sur tous
    les pipelines — d'où le double Nouveau sur Coins Québec."""
    coins = env.ref("doorway_hiba_qualif.crm_team_coins_quebec", raise_if_not_found=False)
    if not coins:
        return
    others = env["crm.team"].sudo().search([("id", "!=", coins.id)])
    if not others:
        return
    stages = env["crm.stage"].sudo().search([])
    for stage in stages:
        if coins in stage.team_ids:
            continue
        if not stage.team_ids:
            stage.write({"team_ids": [(6, 0, others.ids)]})


def post_init_hook(env):
    team = env.ref("doorway_hiba_qualif.crm_team_coins_quebec", raise_if_not_found=False)
    group = env.ref("doorway_hiba_qualif.group_pipeline_tab_coins_quebec", raise_if_not_found=False)
    hiba = env["res.users"].sudo().search([("login", "=", HIBA_LOGIN), ("active", "=", True)], limit=1)
    if not hiba:
        return
    if team:
        if team.user_id != hiba:
            team.sudo().write({"user_id": hiba.id})
        if "doorway_assigned_pipeline_ids" in hiba._fields and team not in hiba.doorway_assigned_pipeline_ids:
            hiba.sudo().write({"doorway_assigned_pipeline_ids": [(4, team.id)]})
        Member = env["crm.team.member"].sudo()
        if hiba.id not in team.crm_team_member_ids.mapped("user_id").ids:
            Member.create({"crm_team_id": team.id, "user_id": hiba.id})
    commands = []
    freelance = env.ref("doorway_hiba_qualif.group_hiba_freelance", raise_if_not_found=False)
    if group and group not in hiba.group_ids:
        commands.append((4, group.id))
    if freelance and freelance not in hiba.group_ids:
        commands.append((4, freelance.id))
    att = env.ref("hr_attendance.group_hr_attendance_own_reader", raise_if_not_found=False)
    if att and att not in hiba.group_ids:
        commands.append((4, att.id))
    manager = env.ref("people_engine.group_manager", raise_if_not_found=False)
    if manager and manager in hiba.group_ids:
        commands.append((3, manager.id))
    employee_g = env.ref("people_engine.group_employee", raise_if_not_found=False)
    if employee_g and employee_g not in hiba.group_ids:
        commands.append((4, employee_g.id))
    if commands:
        hiba.sudo().write({"group_ids": commands})

    company = hiba.company_id
    if company and "attendance_from_systray" in company._fields:
        company.sudo().write({"attendance_from_systray": True})

    emp = env["hr.employee"].sudo().search([("user_id", "=", hiba.id)], limit=1)
    if emp:
        Job = env["hr.job"].sudo()
        job = Job.search([("name", "=", "Qualificatrice Coins Québec")], limit=1)
        if not job:
            job = Job.create({"name": "Qualificatrice Coins Québec", "company_id": emp.company_id.id})
        emp.write({"job_id": job.id})
        profile = env["pe.employee.profile"].sudo().search([("employee_id", "=", emp.id)], limit=1)
        if not profile:
            profile = env["pe.employee.profile"].sudo().create(
                {"employee_id": emp.id, "user_id": hiba.id}
            )
        profile.write(
            {
                "salaire_base": BASE_MAD,
                "devise_remuneration": "MAD",
                "type_remuneration": "honoraire",
                "type_usager_pe": "closeur",
                "hors_paie_maroc": True,
                "description_variable": (
                    "Forfait 5000 MAD / mois. "
                    "Bonus 1000 MAD si moyenne ≥ 5 RDV présents / jour travaillé. "
                    "Bonus 500 MAD par tranche de 5000 USD au-delà de 10 000 USD de CA."
                ),
            }
        )
        Contract = env["pe.employment.contract"].sudo()
        contract = Contract.search(
            [
                ("employee_id", "=", emp.id),
                ("contract_type", "=", "freelance"),
                ("date_end", "=", False),
            ],
            limit=1,
        )
        vals = {
            "employee_id": emp.id,
            "contract_type": "freelance",
            "date_start": fields.Date.from_string("2026-08-01"),
            "salaire_base": BASE_MAD,
            "montant_forfait": BASE_MAD,
            "heures_forfait_min": 0.0,
            "type_facturation": "forfait",
            "devise": "MAD",
            "challenges_eligible": True,
            "description_variable": profile.description_variable,
        }
        if contract:
            contract.write(vals)
        else:
            Contract.create(vals)
        today = fields.Date.context_today(env["pe.payslip.live"])
        env["pe.payslip.live"].sudo()._recalculer_employe(
            emp, today.strftime("%Y-%m"), today.replace(day=1), today
        )
    if hasattr(hiba, "sync_pe_groups_from_profile"):
        hiba.sudo().sync_pe_groups_from_profile()
    manager = env.ref("people_engine.group_manager", raise_if_not_found=False)
    if manager and manager in hiba.group_ids:
        hiba.sudo().with_context(skip_pe_group_resync=True).write(
            {"group_ids": [(3, manager.id)]}
        )
    martin = env["res.users"].sudo().search(
        [("login", "=", MARTIN_LOGIN), ("active", "=", True)], limit=1
    )
    if martin and team:
        Member = env["crm.team.member"].sudo()
        if martin.id not in team.crm_team_member_ids.mapped("user_id").ids:
            Member.create({"crm_team_id": team.id, "user_id": martin.id})
        if group and group not in martin.group_ids:
            martin.sudo().write({"group_ids": [(4, group.id)]})
    extra_company = env["res.company"].sudo().browse(1)
    if extra_company.exists() and extra_company not in hiba.company_ids:
        hiba.sudo().write({"company_ids": [(4, extra_company.id)]})
    _restrict_global_stages_from_coins_quebec(env)
    env.cr.commit()
