# -*- coding: utf-8 -*-
"""Preuve du rôle gestionnaire/membre (Phase 1b).

Vérifie que seul un gestionnaire peut inviter/retirer des membres et éditer
le profil/la facturation de l'organisation, qu'un gestionnaire d'une
organisation ne peut jamais agir sur les membres d'une autre organisation,
et que les garde-fous (auto-retrait, dernier gestionnaire) tiennent.
"""
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "intellix_partner_isolation")
class TestPortalTeamRoles(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        Users = cls.env["res.users"]
        portal_group = cls.env.ref("base.group_portal")
        cls.password = "TestIsolation2026!"

        cls.org_a = Partner.create({"name": "ZZZ Test Team Org A", "is_company": True})
        cls.org_b = Partner.create({"name": "ZZZ Test Team Org B", "is_company": True})

        # Un utilisateur par contact individuel dédié (enfant de la société), jamais
        # directement sur le partenaire commercial : res.users est _inherits de
        # res.partner, passer le partner_id de la société + un name différent dans le
        # même create() écraserait le nom de la société (vérifié empiriquement, corrigé
        # dans portal_team_invite -- ce setup reproduit fidèlement le même schéma).
        def _make_contact(company, name):
            return Partner.create({"name": name, "parent_id": company.id, "company_type": "person"})

        cls.manager_a = Users.create({
            "login": "zzz.team.manager.a@example.com",
            "password": cls.password, "partner_id": _make_contact(cls.org_a, "ZZZ Manager A").id,
            "group_ids": [(6, 0, [portal_group.id])], "is_portal_manager": True,
        })
        cls.member_a = Users.create({
            "login": "zzz.team.member.a@example.com",
            "password": cls.password, "partner_id": _make_contact(cls.org_a, "ZZZ Member A").id,
            "group_ids": [(6, 0, [portal_group.id])], "is_portal_manager": False,
        })
        cls.manager_b = Users.create({
            "login": "zzz.team.manager.b@example.com",
            "password": cls.password, "partner_id": _make_contact(cls.org_b, "ZZZ Manager B").id,
            "group_ids": [(6, 0, [portal_group.id])], "is_portal_manager": True,
        })

    def test_member_cannot_invite(self):
        self.authenticate("zzz.team.member.a@example.com", self.password)
        count_before = self.env["res.users"].sudo().search_count([])
        self.url_open("/my/equipe/inviter", data={
            "csrf_token": self._get_csrf_token("/my/equipe"),
            "name": "Intrus", "email": "zzz.intrus@example.com",
        })
        count_after = self.env["res.users"].sudo().search_count([])
        self.assertEqual(
            count_before, count_after,
            "FUITE: un membre (non gestionnaire) a pu créer un nouvel utilisateur.",
        )

    def test_member_cannot_remove_colleague(self):
        self.authenticate("zzz.team.member.a@example.com", self.password)
        self.url_open(
            "/my/equipe/%d/retirer" % self.manager_a.id,
            data={"csrf_token": self._get_csrf_token("/my/equipe")},
        )
        self.assertTrue(
            self.manager_a.sudo().active,
            "FUITE: un membre (non gestionnaire) a pu retirer un collègue.",
        )

    def test_member_blocked_from_billing(self):
        self.authenticate("zzz.team.member.a@example.com", self.password)
        response = self.url_open("/my/facturation")
        self.assertNotIn(
            "/my/facturation", response.url,
            "FUITE: un membre a accédé à la page de facturation de l'organisation.",
        )

    def test_manager_cannot_remove_across_org(self):
        """Un gestionnaire d'Org A ne doit jamais pouvoir retirer un membre d'Org B."""
        self.authenticate("zzz.team.manager.a@example.com", self.password)
        self.url_open(
            "/my/equipe/%d/retirer" % self.manager_b.id,
            data={"csrf_token": self._get_csrf_token("/my/equipe")},
        )
        self.assertTrue(
            self.manager_b.sudo().active,
            "FUITE CRITIQUE: le gestionnaire d'Org A a pu retirer un utilisateur d'Org B.",
        )

    def test_manager_can_invite_within_own_org(self):
        self.authenticate("zzz.team.manager.a@example.com", self.password)
        self.url_open("/my/equipe/inviter", data={
            "csrf_token": self._get_csrf_token("/my/equipe"),
            "name": "Nouveau Membre A", "email": "zzz.team.new.a@example.com",
        })
        new_user = self.env["res.users"].sudo().search(
            [("login", "=", "zzz.team.new.a@example.com")], limit=1
        )
        self.assertTrue(new_user, "Le gestionnaire n'a pas pu inviter un nouveau membre.")
        self.assertEqual(
            new_user.partner_id.commercial_partner_id.id, self.org_a.id,
            "Le nouveau membre n'est pas rattaché à la bonne organisation.",
        )
        self.assertNotEqual(
            new_user.partner_id.id, self.org_a.id,
            "Le nouveau membre pointe directement sur le partenaire commercial de "
            "l'organisation au lieu d'un contact individuel dédié -- _inherits "
            "écraserait le nom/email de la société au prochain write().",
        )
        self.org_a.invalidate_recordset(["name"])
        self.assertEqual(
            self.org_a.name, "ZZZ Test Team Org A",
            "FUITE DE DONNÉES: le nom de l'organisation a été écrasé par l'invitation "
            "d'un membre (bug _inherits déjà rencontré et corrigé une fois).",
        )
        self.assertFalse(
            new_user.is_portal_manager,
            "Un membre invité ne doit pas être gestionnaire par défaut.",
        )
        new_partner = new_user.partner_id
        new_user.sudo().unlink()
        new_partner.sudo().unlink()

    def test_manager_can_remove_own_member(self):
        Users = self.env["res.users"].sudo()
        Partner = self.env["res.partner"].sudo()
        portal_group = self.env.ref("base.group_portal")
        temp_contact = Partner.create(
            {"name": "ZZZ Temp Member", "parent_id": self.org_a.id, "company_type": "person"}
        )
        temp_member = Users.create({
            "login": "zzz.team.temp.a@example.com",
            "partner_id": temp_contact.id, "group_ids": [(6, 0, [portal_group.id])],
            "is_portal_manager": False,
        })
        self.authenticate("zzz.team.manager.a@example.com", self.password)
        self.url_open(
            "/my/equipe/%d/retirer" % temp_member.id,
            data={"csrf_token": self._get_csrf_token("/my/equipe")},
        )
        self.assertFalse(temp_member.active, "Le gestionnaire n'a pas pu retirer son propre membre.")
        self.assertTrue(temp_member.exists(), "Le membre a été supprimé au lieu d'être archivé.")

    def test_manager_cannot_remove_self(self):
        """Empêche un gestionnaire de se retirer lui-même -- c'est cette garde,
        pas la vérification 'dernier gestionnaire' (structurellement inatteignable
        puisque seul un gestionnaire peut appeler cette route, et le seul cas où il
        serait 'le dernier' est justement quand la cible est lui-même), qui empêche
        en pratique qu'une organisation se retrouve sans aucun gestionnaire."""
        self.authenticate("zzz.team.manager.b@example.com", self.password)
        self.url_open(
            "/my/equipe/%d/retirer" % self.manager_b.id,
            data={"csrf_token": self._get_csrf_token("/my/equipe")},
        )
        self.assertTrue(self.manager_b.sudo().active)

    def test_dave_pichette_is_manager(self):
        dave = self.env["res.users"].search(
            [("login", "=", "dave.pichette@remax-quebec.com")], limit=1
        )
        if not dave:
            self.skipTest("Utilisateur Dave Pichette absent de cette base (environnement de test).")
        self.assertTrue(
            dave.is_portal_manager,
            "Dave Pichette devrait être gestionnaire par défaut (migration data/portal_manager_migration.xml).",
        )

    def _get_csrf_token(self, page_url):
        # Le blob JS `odoo.__session_info__`/`csrf_token` est présent sur toute page
        # frontend, contrairement au champ caché du formulaire d'invitation (rendu
        # seulement pour un gestionnaire) -- fiable quel que soit le rôle testé.
        response = self.url_open(page_url)
        import re
        match = re.search(r'csrf_token:\s*"([^"]+)"', response.text)
        return match.group(1) if match else ""

    @classmethod
    def tearDownClass(cls):
        contact_ids = (
            cls.manager_a.partner_id.id,
            cls.member_a.partner_id.id,
            cls.manager_b.partner_id.id,
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
