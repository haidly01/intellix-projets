# -*- coding: utf-8 -*-
import logging
import os

from odoo import api, fields, models

from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
    HOSTINGER_MANUAL_ONLY_VICIDIAL,
    IA_MANUAL_QUALITY_FLAG,
    IA_MANUAL_QUALITY_VICIDIAL,
)

_logger = logging.getLogger(__name__)

HOSTINGER_FLAG_BY_VICIDIAL = {
    "DW_QCB2C": "/opt/doorway/LEA_QC_HOSTINGER_ONLY.flag",
    "DW_QCB2B": "/opt/doorway/ALEX_HOSTINGER_ONLY.flag",
}

PIPELINE_BY_VICIDIAL = {
    "DW_QCB2B": "driven",
    "DW_FRB2C": "renovation",
    "DW_FRB2B": "marketing",
    "DW_LEAFR": "marketing",
}



class DoorwayCampaignOperational(models.Model):
    _inherit = "doorway.campaign"

    dial_site = fields.Selection(
        [
            ("prod", "PROD France"),
            ("hostinger", "Hostinger QC"),
            ("off", "Arrêté"),
        ],
        string="Site de dial",
        compute="_compute_operational_fields",
        store=True,
    )
    vicidial_mysql_active = fields.Boolean(
        string="VICIdial active",
        compute="_compute_operational_fields",
        store=True,
    )
    vicidial_adl = fields.Integer(
        string="ADL VICIdial",
        compute="_compute_operational_fields",
        store=True,
    )
    vicidial_remote_lines = fields.Integer(
        string="Lignes remote IA",
        compute="_compute_operational_fields",
        store=True,
    )
    is_dialing_prod = fields.Boolean(
        string="En dial PROD",
        compute="_compute_operational_fields",
        store=True,
        help="Numérotation active sur le serveur PROD (ADL > 0 ou remote agent actif).",
    )
    operational_label = fields.Char(
        string="Statut opérationnel",
        compute="_compute_operational_fields",
        store=True,
    )

    @api.model
    def _hostinger_only_vicidial_ids(self):
        return {
            vid
            for vid, path in HOSTINGER_FLAG_BY_VICIDIAL.items()
            if path and os.path.isfile(path)
        }

    @api.model
    def _vicidial_operational_meta(self, vicidial_ids=None):
        svc = self._vicidial_svc()
        if not svc.is_available():
            return {}
        ids = [v for v in (vicidial_ids or []) if v]
        if not ids:
            return {}
        return svc.get_campaign_operational_meta_batch(ids)

    @api.depends("vicidial_campaign_id", "state")
    def _compute_operational_fields(self):
        hostinger_ids = self._hostinger_only_vicidial_ids()
        vicidial_ids = [
            (rec.vicidial_campaign_id or "")[:8]
            for rec in self
            if rec.vicidial_campaign_id
        ]
        meta = self._vicidial_operational_meta(list(set(vicidial_ids)))
        quality_manual = os.path.isfile(IA_MANUAL_QUALITY_FLAG)
        for rec in self:
            vid = (rec.vicidial_campaign_id or "")[:8]
            row = meta.get(vid, {})
            mysql_active = row.get("active") == "Y"
            adl = int(row.get("auto_dial_level") or 0)
            remote_lines = int(row.get("remote_lines") or 0)
            manual_ia = (
                quality_manual and vid in IA_MANUAL_QUALITY_VICIDIAL
            )
            rec.vicidial_mysql_active = mysql_active
            rec.vicidial_adl = adl
            rec.vicidial_remote_lines = remote_lines
            if vid in hostinger_ids:
                rec.dial_site = "hostinger"
                rec.is_dialing_prod = False
                if manual_ia and mysql_active and remote_lines > 0:
                    rec.operational_label = "Manuel qualité (actif)"
                elif mysql_active and remote_lines > 0:
                    rec.operational_label = "Manuel Hostinger (actif)"
                elif mysql_active:
                    rec.operational_label = "Hostinger actif (sans agent)"
                else:
                    rec.operational_label = "Hostinger arrêté"
            elif manual_ia and mysql_active and remote_lines > 0:
                rec.dial_site = "prod" if vid not in hostinger_ids else "hostinger"
                rec.is_dialing_prod = False
                rec.operational_label = "Manuel qualité (actif)"
            elif mysql_active and adl > 0:
                rec.dial_site = "prod"
                rec.is_dialing_prod = True
                rec.operational_label = "En dial PROD"
            elif mysql_active and remote_lines > 0:
                rec.dial_site = "prod"
                rec.is_dialing_prod = False
                rec.operational_label = "Manuel PROD (actif)"
            elif mysql_active:
                rec.dial_site = "prod"
                rec.is_dialing_prod = False
                rec.operational_label = "Prêt PROD (ADL=0)"
            else:
                rec.dial_site = "off"
                rec.is_dialing_prod = False
                rec.operational_label = "Arrêté PROD"

    @api.model
    def cron_sync_all_campaigns(self):
        """Aligne statut Odoo + champs opérationnels sur l'état VICIdial réel."""
        campaigns = self.search([("vicidial_campaign_id", "!=", False)])
        if not campaigns:
            return True
        hostinger_ids = self._hostinger_only_vicidial_ids()
        meta = self._vicidial_operational_meta(
            [(c.vicidial_campaign_id or "")[:8] for c in campaigns]
        )
        for camp in campaigns:
            vid = (camp.vicidial_campaign_id or "")[:8]
            row = meta.get(vid, {})
            mysql_active = row.get("active") == "Y"
            adl = int(row.get("auto_dial_level") or 0)
            remote_lines = int(row.get("remote_lines") or 0)
            vals = {}
            expected_pipeline = PIPELINE_BY_VICIDIAL.get(vid)
            if expected_pipeline and camp.pipeline != expected_pipeline:
                vals["pipeline"] = expected_pipeline
            manual_ia = (
                vid in IA_MANUAL_QUALITY_VICIDIAL
                and os.path.isfile(IA_MANUAL_QUALITY_FLAG)
            )
            if vid in hostinger_ids:
                manual_only = (
                    vid in HOSTINGER_MANUAL_ONLY_VICIDIAL
                    or manual_ia
                    or camp.auto_dial_mode in ("preview", "manual")
                )
                if mysql_active and manual_only and remote_lines > 0:
                    if camp.state in ("paused", "draft", "completed"):
                        vals["state"] = "active"
                    if camp.dial_level != 0:
                        vals["dial_level"] = 0
                    if camp.auto_dial_mode not in ("preview", "manual"):
                        vals["auto_dial_mode"] = "preview"
                elif not mysql_active and camp.state in ("active", "ready"):
                    vals["state"] = "paused"
            elif manual_ia and mysql_active and remote_lines > 0:
                if camp.state in ("paused", "draft", "completed"):
                    vals["state"] = "active"
                if camp.dial_level != 0:
                    vals["dial_level"] = 0
                if camp.auto_dial_mode not in ("preview", "manual"):
                    vals["auto_dial_mode"] = "preview"
            elif mysql_active and (adl > 0 or remote_lines > 0):
                if camp.state in ("ready", "paused", "draft"):
                    vals["state"] = "active"
            elif mysql_active and camp.state == "active" and adl <= 0 and remote_lines <= 0:
                vals["state"] = "ready"
            elif not mysql_active and camp.state == "active":
                vals["state"] = "paused"
            if vals:
                camp.write(vals)
            if manual_ia and adl > 0:
                svc = self._vicidial_svc()
                svc.ensure_ia_manual_quality(vid, clear_hopper=True)
                if camp.dial_level != 0 or camp.auto_dial_mode not in ("preview", "manual"):
                    camp.write({"dial_level": 0, "auto_dial_mode": "preview"})
            if vid in hostinger_ids:
                adl_host = int(row.get("auto_dial_level") or 0)
                manual_only = (
                    vid in HOSTINGER_MANUAL_ONLY_VICIDIAL
                    or manual_ia
                    or camp.auto_dial_mode == "preview"
                )
                if manual_only and adl_host > 0:
                    svc = self._vicidial_svc()
                    svc.ensure_hostinger_manual_only(vid, clear_hopper=True)
                    if camp.dial_level != 0:
                        camp.write({"dial_level": 0, "auto_dial_mode": "preview"})
        campaigns._compute_operational_fields()
        return True
