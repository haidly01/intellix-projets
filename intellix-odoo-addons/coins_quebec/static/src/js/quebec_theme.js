/** @odoo-module **/

/**
 * Scope marque Coins Québec : classe html/body.o_cq_brand uniquement
 * quand l'app courante est coins_quebec.menu_cq_root (ou une action
 * coins.quebec.*). Retirée dès qu'on change d'app — le thème Odoo
 * des autres marques n'est pas touché.
 */
import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";

const CQ_ROOT = "coins_quebec.menu_cq_root";

function _actionLooksCq(action) {
    if (!action) {
        return false;
    }
    const xmlid = action.xml_id || "";
    if (xmlid.indexOf("coins_quebec.") === 0) {
        return true;
    }
    const model = action.res_model || "";
    return model.indexOf("coins.quebec") === 0;
}

const CQ_SUN_SVG =
    '<svg class="o_cq_nav_logo" width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">' +
    '<circle cx="11" cy="11" r="9.5" stroke="#d9a441" stroke-width="1.3"/>' +
    '<path d="M11 2 L11 20 M2 11 L20 11 M4.5 4.5 L17.5 17.5 M17.5 4.5 L4.5 17.5" stroke="#d9a441" stroke-width="0.6" opacity="0.5"/>' +
    '<circle cx="11" cy="11" r="2.3" fill="#d9a441"/>' +
    "</svg>";

function _syncCqHeaderLogo(active) {
    const brand = document.querySelector(
        ".o_main_navbar .o_menu_brand, .o_navbar .o_menu_brand, header.o_navbar .o_menu_brand"
    );
    if (!brand) {
        return;
    }
    const existing = brand.querySelector(".o_cq_nav_logo");
    if (active && !existing) {
        brand.insertAdjacentHTML("afterbegin", CQ_SUN_SVG);
    } else if (!active && existing) {
        existing.remove();
    }
}

function _applyCqBrand(active) {
    const root = document.documentElement;
    const body = document.body;
    const client = document.querySelector(".o_web_client");
    root.classList.toggle("o_cq_brand", active);
    if (body) {
        body.classList.toggle("o_cq_brand", active);
    }
    if (client) {
        client.classList.toggle("o_cq_brand", active);
    }
    _syncCqHeaderLogo(active);
}

patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        this._cqSyncTimer = null;
        const schedule = () => this._scheduleCqBrandSync();
        useBus(this.env.bus, "MENUS:APP-CHANGED", schedule);
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", schedule);
        onMounted(schedule);
    },

    _scheduleCqBrandSync() {
        if (this._cqSyncTimer) {
            return;
        }
        this._cqSyncTimer = setTimeout(() => {
            this._cqSyncTimer = null;
            this._applyCqBrandDom();
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

    _menuIsCq() {
        const svc = this.menuService;
        if (!svc || !svc.getCurrentApp) {
            return false;
        }
        const app = svc.getCurrentApp();
        if (!app) {
            return false;
        }
        if (app.xmlid === CQ_ROOT || (app.xmlid || "").indexOf("coins_quebec.") === 0) {
            return true;
        }
        const name = (app.name || "").toLowerCase();
        return name.indexOf("coins québec") !== -1 || name.indexOf("coins quebec") !== -1;
    },

    _computeIsCqApp() {
        const svc = this.actionService;
        const action = svc && svc.currentController && svc.currentController.action;
        if (_actionLooksCq(action)) {
            return true;
        }
        if (action) {
            const model = action.res_model || "";
            const xmlid = action.xml_id || "";
            const otherModule =
                (model && model.indexOf("coins.quebec") !== 0) ||
                (xmlid && xmlid.indexOf("coins_quebec.") !== 0 && xmlid.indexOf(".") !== -1);
            if (otherModule && !_actionLooksCq(action)) {
                return false;
            }
        }
        return this._menuIsCq();
    },

    _applyCqBrandDom() {
        let active = false;
        try {
            active = this._computeIsCqApp() && !this._isHomeMenu();
        } catch (_err) {
            active = false;
        }
        _applyCqBrand(active);
    },
});
