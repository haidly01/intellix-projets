# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError

from .mon_coin_ops import portal_ops_payload

_logger = logging.getLogger(__name__)

SESSION_DEMO = "mon_coin_demo"

PORTAL_NAV = [
    ("dash", "/mon-coin", "Analytique", "◐"),
    ("inventaire", "/mon-coin/inventaire", "Inventaire", "▤"),
    ("staff", "/mon-coin/staff", "Staff", "◎"),
    ("boutique", "/mon-coin/boutique", "Boutique en ligne", "◇"),
    ("fidelite", "/mon-coin/fidelite", "Fidélité", "✦"),
    ("fiche", "/mon-coin/fiche", "Ma fiche", "✎"),
]
PORTAL_NAV_MORE = [
    ("boosts", "/mon-coin/boosts", "Boosts"),
    ("finances", "/mon-coin/finances", "Mes finances"),
    ("paiement", "/mon-coin/paiement", "Paiement"),
    ("carte", "/carte", "Voir sur la carte"),
]


class CoinsQuebecMonCoin(http.Controller):
    def _demo_session(self):
        return bool(request.session.get(SESSION_DEMO))

    def _staff_can_demo(self):
        user = request.env.user
        if not user or user._is_public() or getattr(user, "share", False):
            return False
        return user.has_group("coins_quebec.group_coins_quebec_user")

    def _demo_fiche(self):
        Part = request.env["coins.quebec.partenariat"].sudo()
        rec = Part.ensure_mon_coin_demo_data()
        if rec and rec.is_demo and not rec._name_is_protected_real():
            return rec.with_context(mon_coin_demo=True)
        return request.env["coins.quebec.partenariat"]

    def _commercant(self):
        if self._demo_session() and self._staff_can_demo():
            rec = self._demo_fiche()
            if rec:
                return rec
        user = request.env.user
        if not user or user._is_public():
            return request.env["coins.quebec.partenariat"]
        rec = request.env["coins.quebec.partenariat"].search(
            [("portal_user_id", "=", user.id)], limit=1
        )
        if rec and rec.is_demo:
            return rec.with_context(mon_coin_demo=True)
        return rec

    def _require_commercant(self):
        rec = self._commercant()
        if not rec:
            return None
        return rec

    def _login_redirect(self):
        return request.redirect("/mon-coin/login")

    def _ctx(self, rec, page, extra=None):
        ctx = {
            "fiche": rec,
            "page": page,
            "nav": PORTAL_NAV,
            "nav_more": PORTAL_NAV_MORE,
            "ops": portal_ops_payload(rec),
            "csrf_token": request.csrf_token(),
            "flash_ok": request.params.get("ok"),
            "flash_err": request.params.get("err"),
            "demo_mode": bool(rec and rec.is_demo),
            "staff_demo": self._demo_session() and self._staff_can_demo(),
        }
        if extra:
            ctx.update(extra)
        return ctx

    def _authenticate(self, login, password):
        credential = {
            "type": "password",
            "login": (login or "").strip(),
            "password": password or "",
        }
        try:
            request.session.authenticate(request.env, credential)
            return True
        except TypeError:
            try:
                request.session.authenticate(request.db, login, password)
                return True
            except Exception:  # noqa: BLE001
                return False
        except Exception:  # noqa: BLE001
            _logger.exception("mon-coin login")
            return False

    @http.route(
        ["/mon-coin/demo", "/mon-coin/demo/"],
        type="http",
        auth="user",
        methods=["GET"],
        website=False,
    )
    def demo_enter(self, **kw):
        if not self._staff_can_demo():
            return request.redirect("/web")
        rec = self._demo_fiche()
        if not rec:
            return request.redirect("/web")
        request.session[SESSION_DEMO] = True
        return request.redirect("/mon-coin")

    @http.route(
        ["/mon-coin/demo/exit"],
        type="http",
        auth="user",
        methods=["GET"],
        website=False,
    )
    def demo_exit(self, **kw):
        request.session.pop(SESSION_DEMO, None)
        return request.redirect("/web")

    @http.route(
        ["/mon-coin/login", "/mon-coin/login/"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=True,
        website=False,
    )
    def login(self, **kw):
        if request.httprequest.method == "POST":
            login = (kw.get("login") or "").strip()
            password = kw.get("password") or ""
            if self._authenticate(login, password):
                rec = self._commercant()
                if rec:
                    return request.redirect("/mon-coin")
                request.session.logout(keep_db=True)
                return request.render(
                    "coins_quebec.mon_coin_login",
                    {
                        "error": "Ce compte n’est pas lié à une fiche commerçant.",
                        "csrf_token": request.csrf_token(),
                    },
                )
            return request.render(
                "coins_quebec.mon_coin_login",
                {
                    "error": "Courriel ou mot de passe incorrect.",
                    "csrf_token": request.csrf_token(),
                },
            )
        rec = self._commercant()
        if rec:
            return request.redirect("/mon-coin")
        if self._demo_session() and self._staff_can_demo():
            return request.redirect("/mon-coin/demo")
        return request.render(
            "coins_quebec.mon_coin_login",
            {"error": "", "csrf_token": request.csrf_token()},
        )

    @http.route(
        ["/mon-coin/logout"],
        type="http",
        auth="public",
        methods=["GET"],
        website=False,
    )
    def logout(self, **kw):
        request.session.logout(keep_db=True)
        return request.redirect("/mon-coin/login")

    @http.route(
        ["/mon-coin/inscription", "/mon-coin/inscription/"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=True,
        website=False,
    )
    def signup(self, **kw):
        if request.httprequest.method != "POST":
            return request.render(
                "coins_quebec.mon_coin_signup",
                {"error": "", "csrf_token": request.csrf_token()},
            )
        name = (kw.get("name") or "").strip()
        email = (kw.get("email") or "").strip().lower()
        password = kw.get("password") or ""
        if not name or not email or len(password) < 8:
            return request.render(
                "coins_quebec.mon_coin_signup",
                {
                    "error": "Nom, courriel et mot de passe (8 caractères min.) requis.",
                    "csrf_token": request.csrf_token(),
                },
            )
        Part = request.env["coins.quebec.partenariat"].sudo()
        if Part.search([("email", "=", email)], limit=1) or request.env[
            "res.users"
        ].sudo().search([("login", "=", email)], limit=1):
            return request.render(
                "coins_quebec.mon_coin_signup",
                {
                    "error": "Ce courriel a déjà un espace. Connectez-vous.",
                    "csrf_token": request.csrf_token(),
                },
            )
        region = kw.get("region") or "monteregie"
        if region not in dict(Part._fields["region"].selection):
            region = "monteregie"
        ptype = kw.get("type_partenaire") or "resto"
        if ptype not in dict(Part._fields["type_partenaire"].selection):
            ptype = "resto"
        rec = Part.create(
            {
                "name": name,
                "contact_name": (kw.get("contact_name") or "").strip() or name,
                "email": email,
                "phone": (kw.get("phone") or "").strip() or False,
                "region": region,
                "type_partenaire": ptype,
                "city": (kw.get("city") or "").strip() or False,
                "street": (kw.get("street") or "").strip() or False,
                "source": "manuel",
                "stage": "nouveau",
                "publish_state": "draft",
            }
        )
        rec.action_create_portal_user(password=password)
        if self._authenticate(email, password):
            return request.redirect("/mon-coin/fiche?ok=espace")
        return request.redirect("/mon-coin/login")

    @http.route(
        ["/mon-coin", "/mon-coin/", "/mon-coin/dashboard"],
        type="http",
        auth="public",
        website=False,
    )
    def dashboard(self, **kw):
        rec = self._require_commercant()
        if not rec:
            return self._login_redirect()
        return request.render(
            "coins_quebec.mon_coin_dashboard",
            self._ctx(rec, "dash"),
        )

    def _ops_page(self, page, template):
        rec = self._require_commercant()
        if not rec:
            return self._login_redirect()
        return request.render(template, self._ctx(rec, page))

    @http.route(
        ["/mon-coin/inventaire", "/mon-coin/inventaire/"],
        type="http",
        auth="public",
        website=False,
    )
    def inventaire(self, **kw):
        return self._ops_page("inventaire", "coins_quebec.mon_coin_inventaire")

    @http.route(
        ["/mon-coin/staff", "/mon-coin/staff/"],
        type="http",
        auth="public",
        website=False,
    )
    def staff(self, **kw):
        return self._ops_page("staff", "coins_quebec.mon_coin_staff")

    @http.route(
        ["/mon-coin/boutique", "/mon-coin/boutique/"],
        type="http",
        auth="public",
        website=False,
    )
    def boutique(self, **kw):
        return self._ops_page("boutique", "coins_quebec.mon_coin_boutique")

    @http.route(
        ["/mon-coin/fidelite", "/mon-coin/fidelite/"],
        type="http",
        auth="public",
        website=False,
    )
    def fidelite(self, **kw):
        return self._ops_page("fidelite", "coins_quebec.mon_coin_fidelite")

    @http.route(
        ["/mon-coin/fiche", "/mon-coin/fiche/"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=True,
        website=False,
    )
    def fiche(self, **kw):
        rec = self._require_commercant()
        if not rec:
            return self._login_redirect()
        if request.httprequest.method == "POST":
            if rec.is_demo:
                try:
                    self._save_fiche(rec, kw)
                    if kw.get("submit_moderation"):
                        return request.redirect("/mon-coin/fiche?ok=demo_noop")
                    return request.redirect("/mon-coin/fiche?ok=demo_saved")
                except Exception:  # noqa: BLE001
                    _logger.exception("sauvegarde fiche démo mon-coin %s", rec.id)
                    return request.render(
                        "coins_quebec.mon_coin_fiche",
                        self._ctx(rec, "fiche", {"error": "Enregistrement démo impossible."}),
                    )
            try:
                self._save_fiche(rec, kw)
                if kw.get("submit_moderation"):
                    rec.action_submit_moderation()
                    return request.redirect("/mon-coin/fiche?ok=moderation")
                return request.redirect("/mon-coin/fiche?ok=draft")
            except Exception:  # noqa: BLE001
                _logger.exception("sauvegarde fiche mon-coin %s", rec.id)
                return request.render(
                    "coins_quebec.mon_coin_fiche",
                    self._ctx(rec, "fiche", {"error": "Enregistrement impossible."}),
                )
        return request.render(
            "coins_quebec.mon_coin_fiche",
            self._ctx(rec, "fiche"),
        )

    def _save_fiche(self, rec, kw):
        region = kw.get("region") or rec.region
        if region not in dict(rec._fields["region"].selection):
            region = rec.region
        ptype = kw.get("type_partenaire") or rec.type_partenaire
        if ptype not in dict(rec._fields["type_partenaire"].selection):
            ptype = rec.type_partenaire
        vals = {
            "name": (kw.get("name") or rec.name).strip() or rec.name,
            "contact_name": (kw.get("contact_name") or "").strip() or False,
            "phone": (kw.get("phone") or "").strip() or False,
            "email": (kw.get("email") or rec.email or "").strip() or rec.email,
            "region": region,
            "type_partenaire": ptype,
            "city": (kw.get("city") or "").strip() or False,
            "street": (kw.get("street") or "").strip() or False,
            "description": (kw.get("description") or "").strip() or False,
            "video_url": (kw.get("video_url") or "").strip() or False,
        }
        lat = kw.get("partner_lat")
        lng = kw.get("partner_lng")
        if lat:
            try:
                vals["partner_lat"] = float(str(lat).replace(",", "."))
            except ValueError:
                pass
        if lng:
            try:
                vals["partner_lng"] = float(str(lng).replace(",", "."))
            except ValueError:
                pass
        rec.write(vals)
        self._save_lines(rec, "service")
        self._save_lines(rec, "offer")
        self._save_photos(rec)

    def _save_lines(self, rec, kind):
        form = request.httprequest.form
        names = form.getlist("%s_name" % kind)
        prices = form.getlist("%s_price" % kind)
        units = form.getlist("%s_unit" % kind)
        ids = form.getlist("%s_id" % kind)
        Model = request.env[
            "coins.quebec.partenariat.service"
            if kind == "service"
            else "coins.quebec.partenariat.forfait"
        ]
        keep = []
        seq = 10
        for i, name in enumerate(names):
            name = (name or "").strip()
            if not name:
                continue
            line_id = 0
            try:
                line_id = int(ids[i]) if i < len(ids) and ids[i] else 0
            except ValueError:
                line_id = 0
            price = 0.0
            try:
                price = float(str(prices[i] if i < len(prices) else "0").replace(",", ".") or 0)
            except ValueError:
                price = 0.0
            unit = (units[i] if i < len(units) else "") or False
            vals = {
                "partenariat_id": rec.id,
                "name": name,
                "price": price,
                "unit": unit,
                "sequence": seq,
            }
            seq += 10
            line = Model.browse(line_id) if line_id else Model.browse()
            if line.exists() and line.partenariat_id.id == rec.id:
                line.write(vals)
            else:
                line = Model.create(vals)
            keep.append(line.id)
        extras = (rec.service_ids if kind == "service" else rec.offer_ids).filtered(
            lambda r: r.id not in keep
        )
        extras.unlink()

    def _save_photos(self, rec):
        files = request.httprequest.files.getlist("photos")
        Photo = request.env["coins.quebec.partenariat.photo"]
        import base64

        seq = (max(rec.photo_ids.mapped("sequence") or [0]) or 0) + 10
        for upload in files:
            raw = upload.read() if upload else b""
            if not raw or len(raw) > 6 * 1024 * 1024:
                continue
            Photo.create(
                {
                    "partenariat_id": rec.id,
                    "image": base64.b64encode(raw),
                    "caption": (upload.filename or "")[:80],
                    "sequence": seq,
                }
            )
            seq += 10

    @http.route(
        ["/mon-coin/boosts", "/mon-coin/boosts/"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=True,
        website=False,
    )
    def boosts(self, tab="radio", **kw):
        rec = self._require_commercant()
        if not rec:
            return self._login_redirect()
        tab = (kw.get("tab") or tab or "radio").strip()
        if tab not in ("radio", "vedette", "influenceurs", "reseaux", "itex", "driven"):
            tab = "radio"
        if request.httprequest.method == "POST":
            kind = (kw.get("kind") or tab).strip()
            note = (kw.get("note") or "").strip()
            if rec.is_demo or self._demo_session():
                return request.redirect("/mon-coin/boosts?tab=%s&ok=demo_noop" % kind)
            try:
                rec.action_request_boost(kind, note)
                return request.redirect("/mon-coin/boosts?tab=%s&ok=boost" % kind)
            except (UserError, AccessError) as exc:
                return request.render(
                    "coins_quebec.mon_coin_boosts",
                    self._ctx(rec, "boosts", {"tab": kind, "error": str(exc)}),
                )
            except Exception:  # noqa: BLE001
                _logger.exception("boost mon-coin %s %s", rec.id, kind)
                return request.render(
                    "coins_quebec.mon_coin_boosts",
                    self._ctx(
                        rec,
                        "boosts",
                        {"tab": kind, "error": "La demande n’a pas pu être créée."},
                    ),
                )
        return request.render(
            "coins_quebec.mon_coin_boosts",
            self._ctx(rec, "boosts", {"tab": tab}),
        )

    @http.route(
        ["/mon-coin/finances", "/mon-coin/finances/"],
        type="http",
        auth="public",
        website=False,
    )
    def finances(self, **kw):
        rec = self._require_commercant()
        if not rec:
            return self._login_redirect()
        payload = rec.portal_finance_payload()
        return request.render(
            "coins_quebec.mon_coin_finances",
            self._ctx(rec, "finances", {"finance": payload}),
        )

    @http.route(
        ["/mon-coin/paiement", "/mon-coin/paiement/"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=True,
        website=False,
    )
    def paiement(self, **kw):
        rec = self._require_commercant()
        if not rec:
            return self._login_redirect()
        if request.httprequest.method == "POST":
            if rec.is_demo or self._demo_session():
                return request.redirect("/mon-coin/paiement?ok=demo_noop")
            if kw.get("clear"):
                rec.clear_authorize_credentials()
                return request.redirect("/mon-coin/paiement?ok=cleared")
            rec.save_authorize_credentials(
                kw.get("authorize_login"), kw.get("authorize_trans_key")
            )
            return request.redirect("/mon-coin/paiement?ok=saved")
        return request.render(
            "coins_quebec.mon_coin_paiement",
            self._ctx(rec, "paiement"),
        )

    @http.route(
        ["/mon-coin/apercu", "/mon-coin/apercu/"],
        type="http",
        auth="public",
        website=False,
    )
    def apercu(self, **kw):
        rec = self._require_commercant()
        if not rec:
            return self._login_redirect()
        if not rec.is_demo:
            rec.increment_pin_click()
        return request.render(
            "coins_quebec.mon_coin_apercu",
            self._ctx(rec, "carte", {"listing": rec.to_public_listing()}),
        )
