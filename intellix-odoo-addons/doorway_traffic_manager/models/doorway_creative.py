# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayCreative(models.Model):
    _name = "doorway.creative"
    _description = "Créatif Traffic Manager"
    _order = "create_date desc"

    campaign_id = fields.Many2one(
        "doorway.traffic.campaign", required=True, ondelete="cascade"
    )
    format = fields.Selection(
        [
            ("image", "Image statique"),
            ("video", "Vidéo"),
            ("carousel", "Carrousel"),
            ("story", "Story"),
            ("reel", "Reel"),
            ("text_ad", "Annonce texte"),
        ],
    )
    headline = fields.Char("Titre (headline)")
    body = fields.Text("Corps du message")
    cta = fields.Char("Call to action")
    brand_angle = fields.Char(
        string="Angle créatif",
        help="Angle marketing lié à la marque et à l'offre (ex. subventions, urgence, preuve sociale).",
    )
    creative_rationale = fields.Text(
        string="Justification IA",
        help="Pourquoi ce créatif est pertinent pour la marque et l'offre.",
    )
    image_url = fields.Char("URL visuel exporté")
    preview_image = fields.Image(
        string="Aperçu visuel",
        max_width=1920,
        max_height=1920,
    )
    video_url = fields.Char("URL vidéo")
    video_thumbnail = fields.Char("Miniature vidéo")
    video_script = fields.Text("Script vidéo (HeyGen)")
    heygen_video_id = fields.Char("HeyGen Video ID")
    media_status = fields.Selection(
        [
            ("none", "Aucun média"),
            ("image_ready", "Image prête"),
            ("video_pending", "Vidéo en cours"),
            ("video_ready", "Vidéo prête"),
        ],
        string="Statut média",
        default="none",
    )
    video_preview_html = fields.Html(
        string="Lecteur vidéo",
        compute="_compute_video_preview_html",
        sanitize=False,
    )
    canva_design_id = fields.Char("Canva Design ID")
    canva_design_url = fields.Char("Lien édition Canva")
    canva_brief = fields.Text(
        string="Brief visuel Canva",
        help="Instructions visuelles ancrées marque pour la création Canva.",
    )
    visual_description = fields.Text(
        string="Description visuelle IA",
        help="Suggestion de mise en page / visuel pour Canva.",
    )
    validation_notes = fields.Text(
        string="Notes de validation",
        help="Commentaires humains avant approbation du créatif.",
    )
    approved_by = fields.Many2one("res.users", string="Approuvé par", readonly=True)
    approved_at = fields.Datetime(string="Approuvé le", readonly=True)

    ai_status = fields.Selection(
        [
            ("proposed", "Proposé par IA"),
            ("approved", "Approuvé"),
            ("rejected", "Ignoré"),
            ("active", "Actif"),
            ("winner", "Gagnant A/B"),
            ("loser", "Perdant A/B"),
        ],
        default="proposed",
    )

    impressions = fields.Integer(readonly=True)
    ctr = fields.Float(readonly=True)
    conversions = fields.Integer(readonly=True)
    cpa = fields.Float(readonly=True)
    ab_test_winner = fields.Boolean("Gagnant A/B", readonly=True)

    def _compute_video_preview_html(self):
        for rec in self:
            if rec.video_url:
                rec.video_preview_html = (
                    '<video controls preload="metadata" '
                    'style="max-width:100%%;border-radius:8px">'
                    '<source src="%s" type="video/mp4"/>'
                    "</video>"
                ) % rec.video_url
            elif rec.format in ("video", "reel", "story"):
                script = (rec.video_script or rec.body or rec.headline or "").strip()
                script_block = (
                    "<p class='text-muted mb-2'>%s</p>" % script[:400]
                    if script
                    else ""
                )
                status = dict(rec._fields["media_status"].selection).get(
                    rec.media_status, rec.media_status
                )
                rec.video_preview_html = (
                    "<div class='doorway_video_placeholder p-3 rounded' "
                    "style='background:#1e293b;color:#f8fafc'>"
                    "<p class='mb-2'><i class='fa fa-video-camera'></i> "
                    "<b>Vidéo en préparation</b> — %s</p>"
                    "%s"
                    "<p class='small mb-0'>Cliquez « Générer vidéo HeyGen » "
                    "ou configurez <code>doorway_social_ia.heygen_api_key</code>.</p>"
                    "</div>"
                ) % (status, script_block)
            else:
                rec.video_preview_html = False

    def action_generate_canva_design(self):
        Canva = self.env["doorway.traffic.canva.service"]
        result = None
        for creative in self:
            result = Canva.generate_creative_design(creative)
        return result or {"status": "skipped", "message": ""}

    def action_generate_video(self):
        Heygen = self.env["doorway.traffic.heygen.service"]
        for creative in self:
            Heygen.generate_creative_video(creative)
        return True

    def action_refresh_preview(self):
        Media = self.env["doorway.traffic.media.service"]
        for creative in self:
            Media.ensure_creative_preview(creative)
        return True

    def action_open_canva(self):
        self.ensure_one()
        if not self.canva_design_url:
            raise UserError(
                _("Aucun lien Canva — générez le visuel ou renseignez canva_design_url.")
            )
        return {
            "type": "ir.actions.act_url",
            "url": self.canva_design_url,
            "target": "new",
        }

    def action_approve(self):
        for creative in self:
            if creative.ai_status != "proposed":
                continue
            creative.write({
                "ai_status": "approved",
                "approved_by": self.env.user.id,
                "approved_at": fields.Datetime.now(),
            })
            note = creative.validation_notes or _("Validé sans commentaire.")
            creative.campaign_id.message_post(
                body=_("Créatif approuvé : <b>%s</b><br/>%s") % (
                    creative.headline or "—",
                    note,
                )
            )
        return True

    def action_reject(self):
        self.write({"ai_status": "rejected"})
        return True

    def action_activate(self):
        for creative in self:
            if creative.ai_status != "approved":
                raise UserError(
                    _("Seuls les créatifs approuvés peuvent être activés — %s")
                    % (creative.headline or creative.id)
                )
        self.write({"ai_status": "active"})
        return True

    @api.model
    def get_creatives_grid(self, filters=None, format=None, status=None):
        filters = dict(filters or {})
        if format:
            filters["format"] = format
        if status:
            filters["status"] = status
        domain = [("ai_status", "in", ("proposed", "approved", "active", "winner", "loser"))]
        if filters.get("format") == "image":
            domain.append(("format", "in", ("image", "carousel")))
        elif filters.get("format") == "video":
            domain.append(("format", "in", ("video", "reel", "story")))
        if filters.get("status") == "winner":
            domain.append(("ai_status", "=", "winner"))
        elif filters.get("status") == "test":
            domain.append(("ai_status", "in", ("proposed", "approved")))
        elif filters.get("status") == "loser":
            domain.append(("ai_status", "=", "loser"))
        creatives = self.search(domain, order="create_date desc", limit=60)
        status_labels = dict(self._fields["ai_status"].selection)
        rows = []
        for c in creatives:
            rows.append({
                "id": c.id,
                "headline": c.headline or "—",
                "format": c.format,
                "campaign": c.campaign_id.name,
                "campaign_id": c.campaign_id.id,
                "channel": c.campaign_id.channel_id.name or "",
                "ai_status": c.ai_status,
                "ai_status_label": status_labels.get(c.ai_status, ""),
                "ctr": c.ctr,
                "conversions": c.conversions,
                "has_image": bool(c.preview_image),
                "has_video": bool(c.video_url),
                "media_status": c.media_status,
            })
        return {"creatives": rows}

    def action_get_ai_suggestions(self):
        self.ensure_one()
        campaign = self.campaign_id
        Ads = self.env["doorway.traffic.ads.service"]
        if not campaign.creative_brand_analysis:
            Ads.analyze_brand_creatives(campaign)
        ideas = self.env["doorway.traffic.claude.service"].suggest_creatives({
            "brand_name": campaign.foundation_id.brand_name,
            "headline": self.headline,
            "body": self.body,
            "brief": campaign.optimization_brief,
        })
        return ideas.get("creatives", [])[:5] if isinstance(ideas, dict) else []
