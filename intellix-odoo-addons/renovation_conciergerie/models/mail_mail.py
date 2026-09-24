from odoo import api, models, tools


class MailMail(models.Model):
    _inherit = "mail.mail"

    @api.model
    def _generate_sale_open_token(self, mail_id):
        return tools.hmac(self.env(su=True), "renovation-sale-mail-open", mail_id)

    def _get_sale_tracking_url(self):
        self.ensure_one()
        token = self._generate_sale_open_token(self.id)
        return tools.urls.urljoin(
            self.get_base_url(),
            f"renovation/sale/track/{self.id}/{token}/open.gif",
        )

    def _prepare_outgoing_body(self):
        body = super()._prepare_outgoing_body()
        self.ensure_one()
        if body and self.model == "sale.order" and self.res_id:
            tracking_url = self._get_sale_tracking_url()
            body = tools.mail.append_content_to_html(
                body,
                f'<img src="{tracking_url}" width="1" height="1" alt="" style="display:none;"/>',
                plaintext=False,
            )
        return body
