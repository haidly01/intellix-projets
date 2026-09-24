/** @odoo-module **/

/**
 * Scope marque Réno Immobilier : html.o_reno_brand seulement
 * quand l'app / l'action courante est reno_immobilier.
 */
import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";

const SELECTOR = [
    ".o_reno_immo_kanban",
    ".o_reno_immo_dash",
    ".o_reno_ix_dash",
    ".o_reno_immo_list",
    ".o_reno_lead_form",
].join(",");

function _actionLooksReno(action) {
    if (!action) {
        return false;
    }
    const xmlid = action.xml_id || "";
    if (xmlid.indexOf("reno_immobilier.") === 0) {
        return true;
    }
    const tag = action.tag || "";
    if (tag === "reno_immobilier_dashboard") {
        return true;
    }
    const model = action.res_model || "";
    return model === "reno.immobilier.dashboard" || model === "renovation.partner.package";
}

function _applyRenoBrand(active) {
    document.documentElement.classList.toggle("o_reno_brand", active);
    document.documentElement.classList.toggle("o_reno_light_pipeline", active);
    if (document.body) {
        document.body.classList.toggle("o_reno_brand", active);
    }
}

function syncDomFallback() {
    _applyRenoBrand(Boolean(document.querySelector(SELECTOR)));
}

patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        this._renoSyncTimer = null;
        const schedule = () => this._scheduleRenoBrandSync();
        useBus(this.env.bus, "MENUS:APP-CHANGED", schedule);
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", schedule);
        onMounted(schedule);
    },

    _scheduleRenoBrandSync() {
        if (this._renoSyncTimer) {
            return;
        }
        this._renoSyncTimer = setTimeout(() => {
            this._renoSyncTimer = null;
            this._applyRenoBrandDom();
        }, 0);
    },

    _isHomeMenu() {
        const path = (window.location.pathname || "").replace(/\/+$/, "") || "/";
        if (path === "/odoo" || path === "/web") {
            return true;
        }
        return Boolean(
            document.querySelector(".o_home_menu, .o_home_menu_background, .o_app_menu")
        );
    },

    _menuIsReno() {
        const svc = this.menuService;
        if (!svc || !svc.getCurrentApp) {
            return false;
        }
        const app = svc.getCurrentApp();
        if (!app) {
            return false;
        }
        if ((app.xmlid || "").indexOf("reno_immobilier.") === 0) {
            return true;
        }
        const name = (app.name || "").toLowerCase();
        return name.indexOf("réno immobilier") !== -1 || name.indexOf("reno immobilier") !== -1;
    },

    _computeIsRenoApp() {
        const svc = this.actionService;
        const action = svc && svc.currentController && svc.currentController.action;
        if (_actionLooksReno(action)) {
            return true;
        }
        if (action) {
            const model = action.res_model || "";
            const xmlid = action.xml_id || "";
            if (model === "crm.lead" && this._menuIsReno()) {
                return true;
            }
            if (model === "res.partner" && this._menuIsReno()) {
                return true;
            }
            const other =
                xmlid &&
                xmlid.indexOf("reno_immobilier.") !== 0 &&
                xmlid.indexOf(".") !== -1 &&
                model !== "crm.lead" &&
                model !== "res.partner";
            if (other) {
                return false;
            }
        }
        return this._menuIsReno();
    },

    _applyRenoBrandDom() {
        let active = false;
        try {
            active = this._computeIsRenoApp() && !this._isHomeMenu();
        } catch (_err) {
            active = Boolean(document.querySelector(SELECTOR));
        }
        _applyRenoBrand(active);
    },
});

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncDomFallback);
} else {
    syncDomFallback();
}
