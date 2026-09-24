# -*- coding: utf-8 -*-
"""Preuve d'isolation entre organisations partenaires (Phase 1a).

Crée 2 sociétés partenaires factices (A et B), chacune avec un utilisateur
portail et un mandat de lead, puis vérifie qu'une recherche ORM standard
(SANS sudo()) par l'utilisateur A ne retourne jamais les données de B —
à la fois via un appel modèle direct (ORM / RPC-style search_read) et via
les routes HTTP du portail (/my/leads, /my/leads/<id>).
"""
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "intellix_partner_isolation")
class TestPartnerLeadIsolation(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        Mandate = cls.env["intellix.partner.lead.mandate"]
        portal_group = cls.env.ref("base.group_portal")

        cls.org_a = Partner.create({"name": "ZZZ Test Isolation Org A", "is_company": True})
        cls.org_b = Partner.create({"name": "ZZZ Test Isolation Org B", "is_company": True})

        cls.password = "TestIsolation2026!"

        cls.user_a = cls.env["res.users"].create({
            "name": "ZZZ Portail Test A",
            "login": "zzz.test.isolation.a@example.com",
            "password": cls.password,
            "partner_id": cls.org_a.id,
            "group_ids": [(6, 0, [portal_group.id])],
            # Gestionnaire : ce test vérifie l'isolation d'ORGANISATION sur /my/leads (Phase 1a),
            # pas le filtrage par membre (couvert séparément par test_crm_leads.py, Phase 2).
            # Sans ça, un non-gestionnaire ne verrait que ses leads assignés -- 0 ici, faussant
            # la vérification "voit A, pas B".
            "is_portal_manager": True,
        })
        cls.user_b = cls.env["res.users"].create({
            "name": "ZZZ Portail Test B",
            "login": "zzz.test.isolation.b@example.com",
            "password": cls.password,
            "partner_id": cls.org_b.id,
            "group_ids": [(6, 0, [portal_group.id])],
        })

        cls.mandate_a = Mandate.create({
            "name": "Lead confidentiel Org A",
            "partner_id": cls.org_a.id,
            "status": "nouveau",
            "city": "Montreal",
        })
        cls.mandate_b = Mandate.create({
            "name": "Lead confidentiel Org B",
            "partner_id": cls.org_b.id,
            "status": "nouveau",
            "city": "Quebec",
        })

    # ---- 1) ORM direct, sans sudo() ----------------------------------

    def test_orm_search_no_sudo_isolates_partners(self):
        mandate_as_a = self.env["intellix.partner.lead.mandate"].with_user(self.user_a)
        results = mandate_as_a.search([])
        self.assertIn(self.mandate_a.id, results.ids)
        self.assertNotIn(
            self.mandate_b.id, results.ids,
            "FUITE ORM: l'utilisateur A voit un mandat de l'organisation B.",
        )

        with self.assertRaises(
            AccessError,
            msg="FUITE ORM: browse+lecture d'un mandat de B par A n'a pas levé AccessError.",
        ):
            _ = mandate_as_a.browse(self.mandate_b.id).name

    # ---- 2) Appel RPC direct au modèle (search_read) ------------------

    def test_rpc_direct_model_call_isolates_partners(self):
        data = self.env["intellix.partner.lead.mandate"].with_user(self.user_a).search_read(
            [], ["id", "name", "partner_id"]
        )
        ids = [row["id"] for row in data]
        self.assertIn(self.mandate_a.id, ids)
        self.assertNotIn(
            self.mandate_b.id, ids,
            "FUITE RPC: search_read côté A retourne un mandat de l'organisation B.",
        )

    # ---- 3) Routes du contrôleur portail -------------------------------

    def test_portal_route_leads_dashboard_isolates_partners(self):
        self.authenticate("zzz.test.isolation.a@example.com", self.password)
        response = self.url_open("/my/leads")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Lead confidentiel Org A", body)
        self.assertNotIn(
            "Lead confidentiel Org B", body,
            "FUITE UI: la page /my/leads de A affiche un lead de l'organisation B.",
        )

    def test_portal_route_lead_detail_blocks_other_org(self):
        self.authenticate("zzz.test.isolation.a@example.com", self.password)
        response = self.url_open("/my/leads/%d" % self.mandate_b.id)
        # 404 (request.not_found() du contrôleur) ou 403 (AccessError de la ir.rule
        # remontée par le dispatcher HTTP quand mandate.partner_id est lu sur un
        # enregistrement non couvert par rule_mandate_portal_partner) sont tous deux
        # des refus d'accès valides. Seul un 200 constituerait une fuite.
        self.assertIn(
            response.status_code, (403, 404),
            "FUITE: A peut accéder au détail d'un mandat appartenant à l'organisation B "
            "(status=%s)." % response.status_code,
        )

    # ---- 4) Non-régression Dave Pichette --------------------------------

    def test_dave_pichette_access_preserved(self):
        """Non-régression : le partenaire réel Dave Pichette Immo garde un accès
        fonctionnel (groupe renovation_conciergerie.group_renovation_partner,
        sans base.group_portal) après l'élargissement des ir.rule."""
        dave = self.env["res.users"].search([("login", "=", "dave.pichette@remax-quebec.com")], limit=1)
        if not dave:
            self.skipTest("Utilisateur Dave Pichette absent de cette base (environnement de test).")
        self.assertTrue(dave.has_group("renovation_conciergerie.group_renovation_partner"))
        self.assertFalse(dave.has_group("base.group_portal"))
        # Doit pouvoir chercher (même vide) sans AccessError, sans sudo().
        try:
            self.env["intellix.partner.lead.mandate"].with_user(dave).search([])
        except AccessError as exc:
            self.fail("Dave Pichette n'a plus accès à intellix.partner.lead.mandate: %s" % exc)

    # ---- 5) Preuve ACL : écriture profil, sudo() requis et suffisant --------

    def test_portal_group_user_can_save_profile(self):
        """base.group_portal : ir.model.access.csv n'accorde PAS perm_write sur
        res.partner à ce groupe (vérifié dans base/security/ir.model.access.csv :
        access_res_partner_portal a write=0). Sans sudo(), l'écriture doit donc
        échouer -- c'est exactement pourquoi portal_profile/portal_zone_add/
        portal_zone_remove conservent sudo() sur partner.write(). Avec sudo()
        (= code réel du contrôleur), la sauvegarde doit réussir."""
        partner_as_a = self.org_a.with_user(self.user_a)
        with self.assertRaises(
            AccessError,
            msg="L'ACL res.partner accorde maintenant perm_write à group_portal : "
                "revoir la justification du sudo() conservé dans portal_profile.",
        ):
            partner_as_a.write({"city_text": "Laval", "coverage_mode": "city"})

        partner_as_a.sudo().write({"city_text": "Laval", "coverage_mode": "city"})
        self.assertEqual(self.org_a.city_text, "Laval")

    def test_renovation_partner_group_user_can_save_profile(self):
        """renovation_conciergerie.group_renovation_partner (comme Dave, sans
        base.group_portal) : même vérification. ir.model.access.csv n'accorde
        perm_write sur res.partner ni à group_user ni à group_renovation_partner
        (seul group_partner_manager l'a) -- sans sudo(), échec attendu ; avec
        sudo() (code réel), la sauvegarde doit réussir."""
        reno_group = self.env.ref("renovation_conciergerie.group_renovation_partner")
        org_reno = self.env["res.partner"].create(
            {"name": "ZZZ Test Isolation Org Reno", "is_company": True}
        )
        user_reno = self.env["res.users"].create({
            "name": "ZZZ Reno Partner Test",
            "login": "zzz.test.isolation.reno@example.com",
            "password": self.password,
            "partner_id": org_reno.id,
            "group_ids": [(6, 0, [reno_group.id])],
        })
        self.assertFalse(user_reno.has_group("base.group_portal"))

        partner_as_reno = org_reno.with_user(user_reno)
        with self.assertRaises(
            AccessError,
            msg="L'ACL res.partner accorde maintenant perm_write à "
                "group_renovation_partner : revoir la justification du sudo() "
                "conservé dans portal_profile.",
        ):
            partner_as_reno.write({"city_text": "Sherbrooke", "coverage_mode": "city"})

        partner_as_reno.sudo().write({"city_text": "Sherbrooke", "coverage_mode": "city"})
        self.assertEqual(org_reno.city_text, "Sherbrooke")

        # res.users a un partner_id requis : supprimer l'utilisateur avant le partenaire.
        user_reno.sudo().unlink()
        org_reno.sudo().unlink()

    @classmethod
    def tearDownClass(cls):
        cls.env.cr.execute(
            "DELETE FROM intellix_partner_lead_mandate WHERE id IN %s",
            ((cls.mandate_a.id, cls.mandate_b.id),),
        )
        cls.env.cr.execute(
            "DELETE FROM res_users WHERE id IN %s",
            ((cls.user_a.id, cls.user_b.id),),
        )
        cls.env.cr.execute(
            "DELETE FROM res_partner WHERE id IN %s",
            ((cls.org_a.id, cls.org_b.id),),
        )
        super().tearDownClass()
