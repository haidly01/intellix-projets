# -*- coding: utf-8 -*-
"""Connexion VICIdial (MySQL port 3307) — mode dégradé si indisponible."""
import logging

_logger = logging.getLogger(__name__)


class VicidialService:
    """Service d'accès aux données VICIdial via MySQL."""

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _get_icp(self, dashboard_key, legacy_key=None, default=""):
        val = self._icp.get_param(dashboard_key)
        if val:
            return val
        if legacy_key:
            val = self._icp.get_param(legacy_key)
            if val:
                return val
        return default

    def _config(self):
        """Lit la configuration depuis ir.config_parameter / odoo-server.conf."""
        g = self._get_icp
        return {
            "host": g("doorway_agents_dashboard.vicidial_db_host", "doorway_agents_ia.vicidial_db_host", "127.0.0.1"),
            "port": int(
                g("doorway_agents_dashboard.vicidial_db_port", "doorway_agents_ia.vicidial_db_port", "3307") or 3307
            ),
            "user": g("doorway_agents_dashboard.vicidial_db_user", "doorway_agents_ia.vicidial_db_user", "vicidial"),
            "password": g(
                "doorway_agents_dashboard.vicidial_db_password",
                "doorway_agents_ia.vicidial_db_password",
                "",
            ),
            "database": g(
                "doorway_agents_dashboard.vicidial_db_name", "doorway_agents_ia.vicidial_db_name", "asterisk"
            ),
        }

    def is_available(self):
        """True si la connexion MySQL VICIdial répond."""
        try:
            conn = self._connect()
            conn.close()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _connect(self):
        """Ouvre une connexion MySQL. Lève une exception si échec."""
        import mysql.connector

        cfg = self._config()
        return mysql.connector.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            connection_timeout=5,
        )

    def _query(self, sql, params=None):
        """Exécute une requête SELECT et renvoie les lignes en dict."""
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            cur.close()
            return rows
        finally:
            conn.close()

    def get_active_calls(self):
        """Récupère les appels actifs (live_channels ou vicidial_live_agents)."""
        if not self.is_available():
            return []
        try:
            return self._query(
                """
                SELECT campaign_id, caller_id, channel, extension, server_ip
                FROM vicidial_live_agents
                LIMIT 200
                """
            )
        except Exception as error:  # noqa: BLE001
            _logger.warning("VICIdial get_active_calls : %s", error)
            return []

    def create_campaign(self, name, campaign_id=None):
        """Crée une campagne VICIdial (si tables présentes)."""
        if not self.is_available():
            return False
        cid = campaign_id or name[:20].replace(" ", "_")
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT IGNORE INTO vicidial_campaigns (campaign_id, campaign_name, active)
                VALUES (%s, %s, 'Y')
                """,
                (cid, name),
            )
            conn.commit()
            cur.close()
            conn.close()
            return cid
        except Exception as error:  # noqa: BLE001
            _logger.warning("VICIdial create_campaign : %s", error)
            return False

    def assign_lead(self, lead_data, campaign_id):
        """Alias : assigne un lead à une campagne VICIdial."""
        return self.assign_lead_to_campaign(lead_data, campaign_id)

    def assign_lead_to_campaign(self, lead_data, campaign_id):
        """Ajoute un lead dans vicidial_list (champs minimaux)."""
        if not self.is_available() or not campaign_id:
            return False
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO vicidial_list (
                    entry_date, status, user, vendor_lead_code,
                    phone_number, first_name, last_name, campaign_id
                ) VALUES (NOW(), 'NEW', 'ODOO', %s, %s, %s, %s, %s)
                """,
                (
                    lead_data.get("vendor_code", "ODOO"),
                    lead_data.get("phone", ""),
                    lead_data.get("first_name", ""),
                    lead_data.get("last_name", ""),
                    campaign_id,
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
            return True
        except Exception as error:  # noqa: BLE001
            _logger.warning("VICIdial assign_lead : %s", error)
            return False

    def get_call_stats(self, campaign_id=None):
        """Statistiques d'appels du jour (vicidial_log)."""
        if not self.is_available():
            return {}
        try:
            domain = ""
            params = []
            if campaign_id:
                domain = " AND campaign_id = %s"
                params.append(campaign_id)
            rows = self._query(
                f"""
                SELECT COUNT(*) AS total_calls,
                       SUM(IF(length_in_sec > 0, 1, 0)) AS answered
                FROM vicidial_log
                WHERE call_date >= CURDATE(){domain}
                """,
                params,
            )
            return rows[0] if rows else {}
        except Exception as error:  # noqa: BLE001
            _logger.warning("VICIdial get_call_stats : %s", error)
            return {}

    def sync_with_odoo(self):
        """Synchronise les appels terminés récents vers doorway.call.session."""
        CallSession = self.env["doorway.call.session"].sudo()
        return CallSession.sync_from_vicidial()
