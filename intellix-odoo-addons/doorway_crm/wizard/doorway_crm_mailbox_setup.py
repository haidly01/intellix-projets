# -*- coding: utf-8 -*-

from odoo import _, api, fields, models

from odoo.exceptions import UserError





class DoorwayCrmMailboxSetup(models.TransientModel):

    _name = "doorway.crm.mailbox.setup"

    _description = "Configuration boîte mail CRM"



    mailbox_id = fields.Many2one("doorway.crm.mailbox", string="Boîte existante")

    name = fields.Char(string="Libellé")

    email = fields.Char(string="Adresse e-mail", required=True)

    password = fields.Char(string="Mot de passe")

    imap_server = fields.Char(default="imap.hostinger.com", required=True)

    imap_port = fields.Integer(default=993, required=True)

    smtp_server = fields.Char(default="smtp.hostinger.com", required=True)

    smtp_port = fields.Integer(default=465, required=True)

    smtp_encryption = fields.Selection(

        [("ssl", "SSL/TLS"), ("starttls", "STARTTLS"), ("none", "Aucun")],

        default="ssl",

        required=True,

    )

    is_default = fields.Boolean(string="Boîte par défaut (envoi)", default=True)

    create_crm_leads = fields.Boolean(

        string="Créer des pistes CRM (nouveaux expéditeurs)",

        default=False,

    )



    @api.model

    def default_get(self, fields_list):

        res = super().default_get(fields_list)

        mailbox_id = self.env.context.get("default_mailbox_id")

        if mailbox_id:

            mailbox = self.env["doorway.crm.mailbox"].browse(mailbox_id)

            if mailbox.exists():

                res.update({

                    "mailbox_id": mailbox.id,

                    "name": mailbox.name,

                    "email": mailbox.email,

                    "imap_server": mailbox.imap_server,

                    "imap_port": mailbox.imap_port,

                    "smtp_server": mailbox.smtp_server,

                    "smtp_port": mailbox.smtp_port,

                    "smtp_encryption": mailbox.smtp_encryption,

                    "is_default": mailbox.is_default,

                    "create_crm_leads": mailbox.create_crm_leads,

                })

                return res

        user = self.env.user

        email = user.email or user.partner_id.email

        if email and "email" in fields_list:

            res.setdefault("email", email)

        res.setdefault("name", _("Ma boîte mail"))

        return res



    def action_save_mailbox(self):

        self.ensure_one()

        if not self.email or "@" not in self.email:

            raise UserError(_("Indiquez une adresse e-mail valide."))

        if not self.password and not self.mailbox_id:

            raise UserError(_("Indiquez le mot de passe de la boîte mail."))



        Mailbox = self.env["doorway.crm.mailbox"]

        duplicate = Mailbox.search([

            ("user_id", "=", self.env.user.id),

            ("email", "=ilike", self.email.strip()),

            ("id", "!=", self.mailbox_id.id if self.mailbox_id else 0),

        ], limit=1)

        if duplicate:
            update_vals = {
                "name": self.name or duplicate.name,
                "imap_server": self.imap_server,
                "imap_port": self.imap_port,
                "smtp_server": self.smtp_server,
                "smtp_port": self.smtp_port,
                "smtp_encryption": self.smtp_encryption,
                "is_default": self.is_default,
                "create_crm_leads": self.create_crm_leads,
            }
            if self.password:
                update_vals["password"] = self.password
            duplicate.with_context(doorway_mailbox_sync=True).write(update_vals)
            return duplicate.action_open_webmail()



        vals = {

            "name": self.name or self.email,

            "user_id": self.env.user.id,

            "email": self.email.strip(),

            "imap_server": self.imap_server,

            "imap_port": self.imap_port,

            "smtp_server": self.smtp_server,

            "smtp_port": self.smtp_port,

            "smtp_encryption": self.smtp_encryption,

            "is_default": self.is_default,

            "create_crm_leads": self.create_crm_leads,

        }

        if self.password:

            vals["password"] = self.password



        sync_ctx = {"doorway_mailbox_sync": True}

        if self.mailbox_id:

            self.mailbox_id.with_context(**sync_ctx).write(vals)

            mailbox = self.mailbox_id

        else:

            mailbox = Mailbox.with_context(**sync_ctx).create(vals)



        if mailbox.is_default:

            try:

                self.env.user.sudo().with_context(**sync_ctx).write({"email": mailbox.email})

            except Exception:

                pass



        return {

            "type": "ir.actions.client",

            "tag": "display_notification",

            "params": {

                "title": _("Boîte mail configurée"),

                "message": _(

                    "La boîte %(email)s est prête. Ouvrez « Mes boîtes mail » pour lire vos messages."

                ) % {"email": mailbox.email},

                "type": "success",

                "sticky": False,

                "next": {

                    "type": "ir.actions.act_window",

                    "res_model": "doorway.crm.mailbox",

                    "res_id": mailbox.id,

                    "view_mode": "form",

                    "target": "current",

                },

            },

        }


