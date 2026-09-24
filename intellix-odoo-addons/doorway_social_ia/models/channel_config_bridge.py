# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwayChannelConfigBridge(models.Model):
    _inherit = "doorway.channel.config"

    social_account_id = fields.Many2one(
        "doorway.social.account",
        string="Compte social lié",
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        default_account = self.env.context.get("default_social_account_id")
        if default_account:
            for vals in vals_list:
                if vals.get("canal") in ("linkedin", "gmb") and not vals.get(
                    "social_account_id"
                ):
                    vals["social_account_id"] = default_account
        records = super().create(vals_list)
        for rec in records.filtered(
            lambda r: r.canal in ("linkedin", "gmb") and r.social_account_id
        ):
            rec.action_sync_social_account()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"access_token", "linkedin_org_id", "linkedin_person_id", "gmb_location_id"} & set(
            vals
        ):
            for rec in self.filtered(
                lambda r: r.canal in ("linkedin", "gmb") and r.social_account_id
            ):
                rec.action_sync_social_account()
        return res

    def action_sync_social_account(self):
        """Synchronise ce canal OAuth vers Réseaux Sociaux IA (profils / établissements)."""
        self.ensure_one()
        platform_map = {"linkedin": "linkedin", "gmb": "gmb"}
        platform = platform_map.get(self.canal)
        if not platform:
            return False

        SocialAccount = self.env["doorway.social.account"].sudo()
        account = self.social_account_id
        if not account:
            account = SocialAccount.search(
                [("platform", "=", platform), ("name", "=", self.name)],
                limit=1,
            )
        vals = {
            "name": self.name,
            "platform": platform,
            "connection_state": "connected" if self.access_token else "disconnected",
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expiry": self.token_expiry,
        }
        if account:
            account.write(vals)
        else:
            account = SocialAccount.create(vals)
            self.sudo().write({"social_account_id": account.id})

        if self.canal == "linkedin":
            urn = ""
            ptype = self.linkedin_profile_type or "organization"
            if ptype == "personal" and self.linkedin_person_id:
                urn = self.linkedin_person_id
                if not urn.startswith("urn:"):
                    urn = "urn:li:person:%s" % urn
            elif self.linkedin_org_id:
                urn = self.linkedin_org_id
                if not urn.startswith("urn:"):
                    urn = "urn:li:organization:%s" % urn
            Profile = self.env["doorway.social.linkedin.profile"].sudo()
            profile = Profile.search(
                [("channel_config_id", "=", self.id)], limit=1
            )
            pdata = {
                "name": self.name,
                "account_id": account.id,
                "channel_config_id": self.id,
                "profile_type": ptype,
                "external_urn": urn,
                "active": self.actif,
            }
            if profile:
                profile.write(pdata)
            else:
                Profile.create(pdata)

        elif self.canal == "gmb":
            Location = self.env["doorway.social.gmb.location"].sudo()
            location = Location.search(
                [("channel_config_id", "=", self.id)], limit=1
            )
            ldata = {
                "name": self.gmb_location_name or self.name,
                "account_id": account.id,
                "channel_config_id": self.id,
                "gmb_account_id": self.gmb_account_id,
                "gmb_location_id": self.gmb_location_id,
                "active": self.actif,
            }
            if location:
                location.write(ldata)
            else:
                Location.create(ldata)
        return True
