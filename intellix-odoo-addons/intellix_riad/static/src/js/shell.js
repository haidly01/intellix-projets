/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { user } from "@web/core/user";
import { riadLabels } from "./labels";

export const NAV_ACTIONS = {
    fleet: { type: "ir.actions.client", tag: "intellix_riad.fleet" },
    channels: { type: "ir.actions.client", tag: "intellix_riad.channels" },
    dashboard: { type: "ir.actions.client", tag: "intellix_riad.dashboard" },
    finance: { type: "ir.actions.client", tag: "intellix_riad.finance" },
    whatsapp: { type: "ir.actions.client", tag: "intellix_riad.whatsapp" },
    reservations: { type: "ir.actions.client", tag: "intellix_riad.calendar" },
    restaurant: { type: "ir.actions.client", tag: "intellix_riad.restaurant" },
    wellness: { type: "ir.actions.client", tag: "intellix_riad.wellness" },
    personnel: { type: "ir.actions.client", tag: "intellix_riad.personnel" },
    mails: { type: "ir.actions.client", tag: "intellix_riad.inbox" },
    social: { type: "ir.actions.client", tag: "intellix_riad.social" },
    events: { type: "ir.actions.client", tag: "intellix_riad.events" },
    settings: { type: "ir.actions.client", tag: "intellix_riad.settings" },
};

function ensureRiadFonts() {
    if (document.getElementById("intellix-riad-fonts")) {
        return;
    }
    const link = document.createElement("link");
    link.id = "intellix-riad-fonts";
    link.rel = "stylesheet";
    link.media = "print";
    link.href =
        "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;1,9..144,400;1,9..144,500&family=Jost:wght@300;400;500;600&display=swap";
    link.onload = () => {
        link.media = "all";
    };
    document.head.appendChild(link);
}

export class RiadShell extends Component {
    static template = "intellix_riad.Shell";
    static props = {
        page: { type: String },
    };

    setup() {
        this.action = this.env.services.action;
        this.orm = this.env.services.orm;
        this.user = user;
        this.labels = riadLabels();
        this.langState = useState({
            lang: (user && user.lang) || "fr_FR",
        });
        ensureRiadFonts();
    }

    get page() {
        return this.props.page;
    }

    get isEnglish() {
        return (this.langState.lang || "").indexOf("en") === 0;
    }

    async setLang(code) {
        if (!this.user || !this.user.userId || !this.orm) {
            return;
        }
        await this.orm.write("res.users", [this.user.userId], { lang: code });
        window.location.reload();
    }

    onNav(page) {
        const target = NAV_ACTIONS[page];
        if (!target || !this.action) {
            return;
        }
        this.action.doAction(target);
    }

    openAllApps() {
        document.body.classList.remove("o_riad_hide_navbar", "o_riad_app_active");
        const root = document.querySelector(".o_web_client");
        if (root) {
            root.classList.remove("o_riad_app_active");
        }
        const appsBtn = document.querySelector(
            ".o_navbar_apps_menu button, .o_menu_toggle, .o_navbar .o_menu_toggle"
        );
        if (appsBtn) {
            appsBtn.click();
            return;
        }
        window.location.assign("/odoo");
    }
}
