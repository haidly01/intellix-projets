/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";

const STORAGE_KEY = "doorway_theme";

function normalize(theme) {
    return theme === "dark" ? "dark" : "light";
}

/**
 * Applique le thème au DOM (instantané, sans rechargement) :
 *  - bascule la classe body o_doorway_light / o_doorway_dark (pilote les tokens)
 *  - aligne data-bs-theme sur <html> (composants Bootstrap)
 *  - met à jour le cache localStorage (application instantanée au prochain chargement)
 */
function applyTheme(theme) {
    const t = normalize(theme);
    const body = document.body;
    if (body) {
        body.classList.toggle("o_doorway_dark", t === "dark");
        body.classList.toggle("o_doorway_light", t === "light");
    }
    if (document.documentElement) {
        document.documentElement.dataset.bsTheme = t;
    }
    try {
        window.localStorage.setItem(STORAGE_KEY, t);
    } catch (e) {
        // localStorage indisponible → on ignore (la classe body reste appliquée)
    }
    return t;
}

/**
 * Thème initial : priorité au compte utilisateur (session, source de vérité
 * res.users.doorway_theme), repli sur le cache localStorage, défaut 'light'.
 */
function initialTheme() {
    let t = session.doorway_theme;
    if (!t) {
        try {
            t = window.localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            t = null;
        }
    }
    return normalize(t);
}

export class DoorwayThemeSwitcher extends Component {
    static template = "intellix_branding.DoorwayThemeSwitcher";
    static props = {};

    setup() {
        this.orm = useService("orm");
        // Réaligne le DOM dès l'affichage (idempotent : le serveur a déjà posé
        // la classe body lors du rendu initial, donc aucun flash).
        this.state = useState({ theme: applyTheme(initialTheme()) });
    }

    get isDark() {
        return this.state.theme === "dark";
    }

    get iconClass() {
        return this.isDark ? "fa fa-sun-o" : "fa fa-moon-o";
    }

    get title() {
        return this.isDark
            ? _t("Passer en thème clair")
            : _t("Passer en thème sombre");
    }

    async onToggle() {
        const next = this.isDark ? "light" : "dark";
        this.state.theme = applyTheme(next);
        // Persistance sur le compte → suit l'utilisateur entre appareils.
        try {
            await this.orm.call("res.users", "write", [
                [user.userId],
                { doorway_theme: next },
            ]);
            session.doorway_theme = next;
        } catch (e) {
            // L'application visuelle reste effective même si l'écriture échoue.
        }
    }
}

registry.category("systray").add(
    "intellix_branding.theme_switcher",
    { Component: DoorwayThemeSwitcher },
    { sequence: 1 }
);
