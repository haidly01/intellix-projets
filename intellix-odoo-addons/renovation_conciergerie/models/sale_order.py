from odoo import _, api, fields, models
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = "sale.order"

    DOORWAY_QUOTATION_EMAIL_FROM = "info@agencedoorway.com"

    quotation_email_opened = fields.Boolean(
        string="Courriel ouvert",
        copy=False,
        readonly=True,
    )
    quotation_email_opened_at = fields.Datetime(
        string="Première ouverture courriel",
        copy=False,
        readonly=True,
    )
    quotation_email_open_count = fields.Integer(
        string="Ouvertures courriel",
        copy=False,
        readonly=True,
        default=0,
    )
    quotation_portal_viewed = fields.Boolean(
        string="Devis lu (portail)",
        copy=False,
        readonly=True,
    )
    quotation_portal_viewed_at = fields.Datetime(
        string="Première lecture devis",
        copy=False,
        readonly=True,
    )
    quotation_portal_view_count = fields.Integer(
        string="Lectures devis",
        copy=False,
        readonly=True,
        default=0,
    )

    def action_quotation_send(self):
        """Devis : expéditeur Hostinger autorisé + modale pour pièces jointes."""
        return super(
            SaleOrder,
            self.with_context(
                default_email_from=self.DOORWAY_QUOTATION_EMAIL_FROM,
            ),
        ).action_quotation_send()

    @api.model
    def _get_quotation_admin_users(self):
        """All internal administrators (group_system)."""
        admin_group = self.env.ref("base.group_system", raise_if_not_found=False)
        if not admin_group:
            return self.env["res.users"]
        return self.env["res.users"].sudo().search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("group_ids", "in", admin_group.id),
            ]
        )

    def _get_quotation_tracking_notify_users(self):
        """Administrators + salesperson assigned to the quotation."""
        self.ensure_one()
        users = self._get_quotation_admin_users()
        salesperson = self.user_id
        if salesperson and salesperson.active and not salesperson.share:
            users |= salesperson
        return users

    def _notify_quotation_tracking_event(self, event):
        """Notify administrators and assigned salesperson (inbox + toast)."""
        self.ensure_one()
        recipients = self._get_quotation_tracking_notify_users()
        if not recipients:
            return

        customer = self.partner_id.display_name
        if event == "email_open":
            title = _("Courriel devis ouvert")
            body = _(
                "Le client %(customer)s a ouvert le courriel du devis %(order)s.",
                customer=customer,
                order=self.name,
            )
        elif event == "portal_view":
            title = _("Devis consulté en ligne")
            body = _(
                "Le client %(customer)s a consulté le devis %(order)s sur le portail.",
                customer=customer,
                order=self.name,
            )
        else:
            return

        message_body = _(
            "%(body)s<br/>%(link)s",
            body=body,
            link=self._get_html_link(),
        )
        self.sudo().message_post(
            body=message_body,
            subject=title,
            message_type="notification",
            subtype_xmlid="mail.mt_note",
            partner_ids=recipients.partner_id.ids,
        )
        bus_payload = {
            "title": title,
            "message": body,
            "type": "info",
            "sticky": False,
        }
        for user in recipients:
            self.env["bus.bus"]._sendone(
                user.partner_id,
                "simple_notification",
                bus_payload,
            )

    def _register_quotation_email_open(self):
        now = fields.Datetime.now()
        for order in self:
            first_open = not order.quotation_email_opened
            order.sudo().write(
                {
                    "quotation_email_opened": True,
                    "quotation_email_opened_at": order.quotation_email_opened_at or now,
                    "quotation_email_open_count": order.quotation_email_open_count + 1,
                }
            )
            if first_open:
                order._notify_quotation_tracking_event("email_open")

    def _register_quotation_portal_view(self):
        if not request:
            return
        today = fields.Date.today().isoformat()
        now = fields.Datetime.now()
        for order in self:
            session_key = "renovation_view_quote_%s" % order.id
            if request.session.get(session_key) == today:
                continue
            request.session[session_key] = today
            first_view = not order.quotation_portal_viewed
            order.sudo().write(
                {
                    "quotation_portal_viewed": True,
                    "quotation_portal_viewed_at": order.quotation_portal_viewed_at or now,
                    "quotation_portal_view_count": order.quotation_portal_view_count + 1,
                }
            )
            if first_view:
                order._notify_quotation_tracking_event("portal_view")

    def _get_pricelist_from_partner_country(self, partner, company=None):
        if not partner:
            return False
        currency_code = partner._get_default_currency_code_for_country(partner.country_id)
        return partner._get_pricelist_for_currency_code(
            currency_code, company=company or self.company_id
        )

    @api.onchange("partner_id")
    def _onchange_partner_id_set_currency_pricelist(self):
        for order in self:
            pricelist = order._get_pricelist_from_partner_country(
                order.partner_id, company=order.company_id
            )
            if pricelist:
                order.pricelist_id = pricelist

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            pricelist = order._get_pricelist_from_partner_country(
                order.partner_id, company=order.company_id
            )
            if pricelist and order.pricelist_id != pricelist:
                order.pricelist_id = pricelist
        return orders

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals:
            for order in self:
                pricelist = order._get_pricelist_from_partner_country(
                    order.partner_id, company=order.company_id
                )
                if pricelist and order.pricelist_id != pricelist:
                    super(SaleOrder, order).write({"pricelist_id": pricelist.id})
        return res
