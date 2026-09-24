# -*- coding: utf-8 -*-
"""Preuve CRM leads (Phase 2).

Vérifie : isolation N-org sur les nouveaux modèles (activité), restriction
gestionnaire/membre sur la réassignation et le changement de statut, et
surtout les deux écarts volontaires par rapport à la maquette :
- aucune transition automatique vers "perdu" après 3 tentatives ;
- taux de closing = vendus / (vendus + perdus), jamais vendus/total.
"""
import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "intellix_partner_isolation")
class TestCrmLeads(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        Users = cls.env["res.users"]
        Mandate = cls.env["intellix.partner.lead.mandate"]
        portal_group = cls.env.ref("base.group_portal")
        cls.password = "TestIsolation2026!"

        cls.org_a = Partner.create({"name": "ZZZ CRM Org A", "is_company": True})
        cls.org_b = Partner.create({"name": "ZZZ CRM Org B", "is_company": True})

        def _contact(company, name):
            return Partner.create({"name": name, "parent_id": company.id, "company_type": "person"})

        cls.manager_a = Users.create({
            "login": "zzz.crm.manager.a@example.com", "password": cls.password,
            "partner_id": _contact(cls.org_a, "ZZZ CRM Manager A").id,
            "group_ids": [(6, 0, [portal_group.id])], "is_portal_manager": True,
        })
        cls.member_a = Users.create({
            "login": "zzz.crm.member.a@example.com", "password": cls.password,
            "partner_id": _contact(cls.org_a, "ZZZ CRM Member A").id,
            "group_ids": [(6, 0, [portal_group.id])], "is_portal_manager": False,
        })
        cls.manager_b = Users.create({
            "login": "zzz.crm.manager.b@example.com", "password": cls.password,
            "partner_id": _contact(cls.org_b, "ZZZ CRM Manager B").id,
            "group_ids": [(6, 0, [portal_group.id])], "is_portal_manager": True,
        })

        cls.lead_a1 = Mandate.create({
            "name": "Lead Org A - membre", "partner_id": cls.org_a.id,
            "status": "nouveau", "assigned_user_id": cls.member_a.id,
        })
        cls.lead_a2 = Mandate.create({
            "name": "Lead Org A - non assigné", "partner_id": cls.org_a.id,
            "status": "nouveau",
        })
        cls.lead_b1 = Mandate.create({
            "name": "Lead Org B confidentiel", "partner_id": cls.org_b.id,
            "status": "nouveau", "assigned_user_id": cls.manager_b.id,
        })

    def _get_csrf_token(self, page_url):
        import re
        response = self.url_open(page_url)
        match = re.search(r'csrf_token:\s*"([^"]+)"', response.text)
        return match.group(1) if match else ""

    def _rpc(self, url, params):
        return self.url_open(
            url,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}),
            headers={"Content-Type": "application/json"},
        ).json().get("result")

    # ---- 1) Isolation croisée sur le nouveau modèle activité ----

    def test_activity_isolation_across_orgs(self):
        Activity = self.env["intellix.partner.lead.activity"]
        act_a = Activity.create({"mandate_id": self.lead_a1.id, "activity_type": "call", "title": "Appel A"})
        act_b = Activity.create({"mandate_id": self.lead_b1.id, "activity_type": "call", "title": "Appel B"})

        visible_to_a = Activity.with_user(self.manager_a).search([])
        self.assertIn(act_a.id, visible_to_a.ids)
        self.assertNotIn(
            act_b.id, visible_to_a.ids,
            "FUITE: le gestionnaire d'Org A voit une activité d'Org B.",
        )
        act_a.unlink()
        act_b.unlink()

    # ---- 2) Réassignation : gestionnaire uniquement, jamais cross-org ----

    def test_member_cannot_reassign(self):
        self.authenticate("zzz.crm.member.a@example.com", self.password)
        token = self._get_csrf_token("/my/leads")
        res = self._rpc("/my/leads/api/reassign", {"mandate_id": self.lead_a2.id, "user_id": self.member_a.id})
        self.assertFalse(res and res.get("ok"), "FUITE: un membre a pu réassigner un lead.")
        self.assertFalse(self.lead_a2.sudo().assigned_user_id)

    def test_manager_cannot_reassign_to_other_org_user(self):
        self.authenticate("zzz.crm.manager.a@example.com", self.password)
        res = self._rpc("/my/leads/api/reassign", {"mandate_id": self.lead_a2.id, "user_id": self.manager_b.id})
        self.assertFalse(
            res and res.get("ok"),
            "FUITE CRITIQUE: le gestionnaire d'Org A a pu assigner un lead à un utilisateur d'Org B.",
        )
        self.assertFalse(self.lead_a2.sudo().assigned_user_id)

    def test_manager_can_reassign_within_org(self):
        self.authenticate("zzz.crm.manager.a@example.com", self.password)
        res = self._rpc("/my/leads/api/reassign", {"mandate_id": self.lead_a2.id, "user_id": self.member_a.id})
        self.assertTrue(res and res.get("ok"))
        self.assertEqual(self.lead_a2.sudo().assigned_user_id.id, self.member_a.id)
        # Nettoyage
        self.lead_a2.sudo().write({"assigned_user_id": False})

    # ---- 3) Membre restreint à ses leads assignés (notes/statut/activité) ----

    def test_member_cannot_touch_unassigned_org_lead(self):
        self.authenticate("zzz.crm.member.a@example.com", self.password)
        res = self._rpc("/my/leads/api/notes", {"mandate_id": self.lead_a2.id, "notes": "intrusion"})
        self.assertFalse(res and res.get("ok"), "Un membre a pu modifier un lead qui ne lui est pas assigné.")
        self.assertFalse(self.lead_a2.sudo().notes)

    def test_member_can_touch_own_assigned_lead(self):
        self.authenticate("zzz.crm.member.a@example.com", self.password)
        res = self._rpc("/my/leads/api/notes", {"mandate_id": self.lead_a1.id, "notes": "note membre"})
        self.assertTrue(res and res.get("ok"))
        self.assertEqual(self.lead_a1.sudo().notes, "note membre")

    # ---- 4) AUCUNE transition automatique vers "perdu" (écart volontaire vs maquette) ----

    def test_no_automatic_perdu_after_three_no_answer(self):
        self.authenticate("zzz.crm.manager.a@example.com", self.password)
        lead = self.env["intellix.partner.lead.mandate"].create({
            "name": "ZZZ Lead 3 tentatives", "partner_id": self.org_a.id, "status": "relance",
        })
        for i in range(3):
            res = self._rpc("/my/leads/api/attempt/create", {
                "mandate_id": lead.id, "date": "2026-09-17", "time": "10:0%d" % i,
                "result": "no_answer", "note": "",
            })
            self.assertTrue(res and res.get("ok"))
        lead.invalidate_recordset(["status"])
        self.assertEqual(
            lead.status, "relance",
            "RÉGRESSION: le statut a basculé automatiquement vers 'perdu' après 3 tentatives "
            "sans réponse -- la consigne exige une décision humaine, jamais automatique.",
        )
        lead.sudo().unlink()

    def test_manual_status_change_to_perdu_works(self):
        self.authenticate("zzz.crm.manager.a@example.com", self.password)
        lead = self.env["intellix.partner.lead.mandate"].create({
            "name": "ZZZ Lead perdu manuel", "partner_id": self.org_a.id, "status": "relance",
        })
        res = self._rpc("/my/leads/api/status", {"mandate_id": lead.id, "status": "perdu"})
        self.assertTrue(res and res.get("ok"))
        lead.invalidate_recordset(["status"])
        self.assertEqual(lead.status, "perdu")
        lead.sudo().unlink()

    def test_interested_result_moves_to_rdv(self):
        self.authenticate("zzz.crm.manager.a@example.com", self.password)
        lead = self.env["intellix.partner.lead.mandate"].create({
            "name": "ZZZ Lead interesse", "partner_id": self.org_a.id, "status": "relance",
        })
        res = self._rpc("/my/leads/api/attempt/create", {
            "mandate_id": lead.id, "date": "2026-09-17", "time": "11:00",
            "result": "interested", "note": "",
        })
        self.assertTrue(res and res.get("ok"))
        lead.invalidate_recordset(["status"])
        self.assertEqual(lead.status, "rdv")
        lead.sudo().unlink()

    # ---- 5) Taux de closing = vendus / (vendus + perdus), jamais vendus/total ----

    def test_close_rate_formula_excludes_open_leads(self):
        Mandate = self.env["intellix.partner.lead.mandate"]
        vendu = Mandate.create({"name": "ZZZ Vendu", "partner_id": self.org_a.id, "status": "vendu"})
        perdu = Mandate.create({"name": "ZZZ Perdu", "partner_id": self.org_a.id, "status": "perdu"})
        # lead_a1, lead_a2 restent "nouveau" -- doivent être EXCLUS du calcul du taux.
        self.authenticate("zzz.crm.manager.a@example.com", self.password)
        response = self.url_open("/my/dashboard")
        self.assertEqual(response.status_code, 200)
        # 1 vendu / (1 vendu + 1 perdu) = 50%, pas 1/(total leads org, qui est bien plus grand).
        self.assertIn("50", response.text, "Le taux de closing affiché ne correspond pas à vendus/(vendus+perdus).")
        (vendu | perdu).sudo().unlink()

    # ---- 6) Dashboard : agrégats jamais mélangés entre organisations ----

    def test_dashboard_kpi_does_not_leak_across_orgs(self):
        self.authenticate("zzz.crm.manager.a@example.com", self.password)
        response = self.url_open("/my/dashboard")
        self.assertNotIn(
            "Lead Org B confidentiel", response.text,
            "FUITE: le tableau de bord d'Org A affiche un lead d'Org B.",
        )

    @classmethod
    def tearDownClass(cls):
        contact_ids = (
            cls.manager_a.partner_id.id, cls.member_a.partner_id.id, cls.manager_b.partner_id.id,
        )
        cls.env.cr.execute(
            "DELETE FROM intellix_partner_lead_activity WHERE mandate_id IN %s",
            ((cls.lead_a1.id, cls.lead_a2.id, cls.lead_b1.id),),
        )
        cls.env.cr.execute(
            "DELETE FROM intellix_partner_lead_attempt WHERE mandate_id IN %s",
            ((cls.lead_a1.id, cls.lead_a2.id, cls.lead_b1.id),),
        )
        cls.env.cr.execute(
            "DELETE FROM intellix_partner_lead_mandate WHERE id IN %s",
            ((cls.lead_a1.id, cls.lead_a2.id, cls.lead_b1.id),),
        )
        cls.env.cr.execute(
            "DELETE FROM res_users WHERE id IN %s",
            ((cls.manager_a.id, cls.member_a.id, cls.manager_b.id),),
        )
        cls.env.cr.execute(
            "DELETE FROM res_partner WHERE id IN %s",
            (contact_ids + (cls.org_a.id, cls.org_b.id),),
        )
        super().tearDownClass()
