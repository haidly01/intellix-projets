# -*- coding: utf-8 -*-
"""Compteur de vues vidéo — badge Tendance (fenêtre glissante 7 jours)."""
from datetime import timedelta

from odoo import api, fields, models


class CoinsFicheVideoView(models.Model):
    _name = "coins.fiche_video.view"
    _description = "Vue vidéo fiche (carte)"
    _order = "viewed_at desc, id desc"

    video_id = fields.Many2one(
        "coins.fiche_video",
        string="Vidéo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    fiche_id = fields.Many2one(
        related="video_id.fiche_id",
        store=True,
        index=True,
    )
    viewed_at = fields.Datetime(
        string="Vu le",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    viewer_key = fields.Char(
        string="Clé spectateur",
        index=True,
        help="Hash IP (ou équivalent) pour le rate-limit soft.",
    )

    @api.model
    def record_view(self, video_id, viewer_key=""):
        """Enregistre une ouverture ; 1 hit / vidéo / viewer_key / 30 min."""
        Video = self.env["coins.fiche_video"].sudo()
        video = Video.browse(int(video_id)).exists()
        if not video or video.statut != "publiee":
            return False
        key = (viewer_key or "")[:64]
        if key:
            since = fields.Datetime.now() - timedelta(minutes=30)
            existing = self.sudo().search_count([
                ("video_id", "=", video.id),
                ("viewer_key", "=", key),
                ("viewed_at", ">=", since),
            ])
            if existing:
                return True
        self.sudo().create({
            "video_id": video.id,
            "viewed_at": fields.Datetime.now(),
            "viewer_key": key or False,
        })
        return True

    @api.model
    def trending_fiche_ids(self, limit=3):
        """Top fiches par vues sur 7 jours glissants."""
        since = fields.Datetime.now() - timedelta(days=7)
        self.env.cr.execute(
            """
            SELECT fiche_id, COUNT(*) AS cnt
              FROM coins_fiche_video_view
             WHERE viewed_at >= %s
               AND fiche_id IS NOT NULL
             GROUP BY fiche_id
             ORDER BY cnt DESC, fiche_id
             LIMIT %s
            """,
            (since, int(limit)),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def cron_prune_old_views(self):
        cutoff = fields.Datetime.now() - timedelta(days=30)
        old = self.sudo().search([("viewed_at", "<", cutoff)])
        old.unlink()
