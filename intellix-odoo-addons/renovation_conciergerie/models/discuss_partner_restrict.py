# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain


class DiscussChannelPartnerRestrict(models.Model):
    _inherit = "discuss.channel"

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        channels = super().search(domain, offset=offset, limit=limit, order=order)
        user = self.env.user
        if not user._is_renovation_partner_user():
            return channels
        return channels._filter_discuss_channels_for_partner()

    def _filter_discuss_channels_for_partner(self):
        """Masque les discussions 1:1/groupes avec des utilisateurs non autorisés."""
        user = self.env.user
        allowed = set(user._get_discuss_allowed_partner_ids())
        my_partner = user.partner_id.id
        kept = self.env["discuss.channel"]
        for channel in self:
            if channel.channel_type == "channel":
                continue
            others = set(channel.channel_member_ids.partner_id.ids) - {my_partner}
            if not others or others <= allowed:
                kept |= channel
        return kept

    @api.model
    def _get_or_create_chat(self, partners_to, pin=True):
        partners = self.env["res.partner"].browse(partners_to).exists()
        self.env.user._check_discuss_partners_allowed(partners)
        return super()._get_or_create_chat(partners_to, pin=pin)

    @api.model
    def _create_group(self, partners_to, default_display_mode=False, name=""):
        if self.env.user._is_renovation_partner_user():
            raise AccessError(
                _("Les partenaires ne peuvent pas créer de groupes de discussion.")
            )
        partners = self.env["res.partner"].browse(list(partners_to)).exists()
        self.env.user._check_discuss_partners_allowed(partners)
        return super()._create_group(
            partners_to, default_display_mode=default_display_mode, name=name
        )

    def _add_members(
        self,
        *,
        guests=None,
        partners=None,
        users=None,
        create_member_params=None,
        invite_to_rtc_call=False,
        post_joined_message=True,
        inviting_partner=None,
    ):
        if self.env.user._is_renovation_partner_user():
            partners = partners or self.env["res.partner"]
            if users:
                partners |= users.partner_id
            self.env.user._check_discuss_partners_allowed(partners)
        return super()._add_members(
            guests=guests,
            partners=partners,
            users=users,
            create_member_params=create_member_params,
            invite_to_rtc_call=invite_to_rtc_call,
            post_joined_message=post_joined_message,
            inviting_partner=inviting_partner,
        )


class ResUsersPartnerVisibility(models.Model):
    _inherit = "res.users"

    @api.model
    def _partner_visibility_filter_user_ids(self):
        if self.env.su or not self.env.user._is_renovation_partner_user():
            return None
        return self.env.user._get_visible_user_ids()

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        allowed = self._partner_visibility_filter_user_ids()
        if allowed is None:
            return super().search(domain, offset=offset, limit=limit, order=order)
        users = self.sudo().browse(list(allowed))
        if domain:
            users = users.filtered_domain(domain)
        if order:
            users = users.search([("id", "in", users.ids)], order=order)
        if offset:
            users = users[offset:]
        if limit is not None:
            users = users[:limit]
        return users

    @api.model
    def search_count(self, domain, limit=None):
        return len(self.search(domain, limit=limit))

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        allowed = self._partner_visibility_filter_user_ids()
        if allowed is not None:
            domain = Domain.AND([Domain(domain or []), Domain("id", "in", list(allowed))])
        return super().name_search(name, domain=domain, operator=operator, limit=limit)


class ResPartnerDiscussRestrict(models.Model):
    _inherit = "res.partner"

    @api.model
    def _partner_visibility_extra_domain(self):
        """Domaine additionnel pour masquer les autres partenaires rénovation."""
        if self.env.su or not self.env.user._is_renovation_partner_user():
            return None
        hide_ids = self.env.user._get_other_renovation_partner_partner_ids()
        if not hide_ids:
            return None
        return Domain("id", "not in", hide_ids)

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        extra = self._partner_visibility_extra_domain()
        if extra is not None:
            domain = Domain.AND([Domain(domain), extra])
        return super().search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def search_count(self, domain, limit=None):
        extra = self._partner_visibility_extra_domain()
        if extra is not None:
            domain = Domain.AND([Domain(domain), extra])
        return super().search_count(domain, limit=limit)

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        extra = self._partner_visibility_extra_domain()
        if extra is not None:
            domain = Domain.AND([Domain(domain or []), extra])
        return super().name_search(name, domain=domain, operator=operator, limit=limit)

    @api.model
    def _search_for_channel_invite(self, store, search_term, channel_id=None, limit=30):
        if not self.env.user._is_renovation_partner_user():
            return super()._search_for_channel_invite(
                store, search_term, channel_id=channel_id, limit=limit
            )
        allowed = set(self.env.user._get_discuss_allowed_partner_ids())
        domain = Domain.AND(
            [
                Domain("name", "ilike", search_term) | Domain("email", "ilike", search_term),
                Domain("id", "in", list(allowed)),
                Domain("active", "=", True),
            ]
        )
        partners = self.sudo().search(domain, limit=limit)
        channel = self.env["discuss.channel"]
        if channel_id:
            channel = channel.browse(int(channel_id))
        partners._search_for_channel_invite_to_store(store, channel)
        return {"count": len(partners), "partner_ids": partners.ids}

    @api.model
    def _search_mention_suggestions(self, domain, limit, extra_domain=None):
        if self.env.user._is_renovation_partner_user():
            allowed_domain = Domain("id", "in", self.env.user._get_discuss_allowed_partner_ids())
            extra_domain = allowed_domain & (extra_domain or Domain.TRUE)
        return super()._search_mention_suggestions(domain, limit, extra_domain=extra_domain)
