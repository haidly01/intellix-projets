/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";

const RIAD_APP_HINTS = ["hébergement", "hebergement", "module riad"];
const RIAD_COMPANION_PREFIXES = ["doorway_messaging.", "doorway_social_ia."];

function _actionLooksRiad(action) {
    if (!action) {
        return false;
    }
    const tag = action.tag || "";
    if (tag.indexOf("intellix_riad.") === 0) {
        return true;
    }
    const xmlid = action.xml_id || "";
    if (xmlid.indexOf("intellix_riad.") === 0) {
        return true;
    }
    const model = action.res_model || "";
    return model.indexOf("intellix.riad") === 0;
}

function _actionIsRiadCompanion(action) {
    if (!action) {
        return false;
    }
    const xmlid = action.xml_id || "";
    const tag = action.tag || "";
    return RIAD_COMPANION_PREFIXES.some(
        (prefix) => xmlid.indexOf(prefix) === 0 || tag.indexOf(prefix) === 0
    );
}

patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        this._riadKeepApps = true;
        this._riadSyncTimer = null;
        const user = this.env.services.user;
        if (user && user.hasGroup && !(user.isAdmin || user.isSystem)) {
            Promise.resolve(user.hasGroup("intellix_riad.group_riad_manager"))
                .then((isManager) => {
                    this._riadKeepApps = Boolean(isManager);
                    this._scheduleRiadChromeSync();
                })
                .catch(() => {
                    this._riadKeepApps = true;
                    this._scheduleRiadChromeSync();
                });
        }
        const schedule = () => this._scheduleRiadChromeSync();
        useBus(this.env.bus, "MENUS:APP-CHANGED", schedule);
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", schedule);
        onMounted(schedule);
    },

    _computeIsRiadApp() {
        const svc = this.actionService;
        if (!svc) {
            return false;
        }
        const action = svc.currentController && svc.currentController.action;
        if (_actionLooksRiad(action)) {
            return true;
        }
        return this._menuIsRiad() && _actionIsRiadCompanion(action);
    },

    _scheduleRiadChromeSync() {
        if (this._riadSyncTimer) {
            return;
        }
        this._riadSyncTimer = setTimeout(() => {
            this._riadSyncTimer = null;
            this._applyRiadDom();
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

    _applyRiadDom() {
        let active = false;
        try {
            active = this._computeIsRiadApp() && !this._isHomeMenu();
        } catch (_err) {
            active = false;
        }
        // Barre Odoo visible (apps + systray) pour Karine et les managers.
        // On ne cache la navbar que pour un accès terrain hébergement seul.
        const hideNavbar = active && this._riadKeepApps === false;
        document.body.classList.toggle("o_riad_app_active", active);
        document.body.classList.toggle("o_riad_hide_navbar", hideNavbar);
        const root = document.querySelector(".o_web_client");
        if (root) {
            root.classList.toggle("o_riad_app_active", active);
        }
        if (!active) {
            document.body.classList.remove("o_riad_app_active", "o_riad_hide_navbar");
            if (root) {
                root.classList.remove("o_riad_app_active");
            }
        }
    },

    _menuIsRiad() {
        if (!this.menuService) {
            return false;
        }
        const app = this.menuService.getCurrentApp();
        if (!app) {
            return false;
        }
        if (app.xmlid === "intellix_riad.menu_riad_root") {
            return true;
        }
        const name = (app.name || "").toLowerCase();
        return RIAD_APP_HINTS.some((hint) => name.indexOf(hint) !== -1);
    },
});
