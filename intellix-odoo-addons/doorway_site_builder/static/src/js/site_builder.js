/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const FORM_FIELDS = [
    "name",
    "language",
    "sector",
    "tone",
    "inspiration",
    "personas",
    "objectives",
    "pages_wanted",
    "set_as_homepage",
];

// Suggestions d'itération rapides affichées dans le panneau de chat.
const CHAT_SUGGESTIONS = [
    "Rends-le plus premium",
    "Ajoute une page Tarifs",
    "Optimise les couleurs",
    "Raccourcis les textes",
];

export class SiteBuilderApp extends Component {
    static template = "doorway_site_builder.App";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.suggestions = CHAT_SUGGESTIONS;
        this.state = useState({
            loading: true,
            generating: false,
            publishing: false,
            data: null,
            activeTab: "preview",
            projectsOpen: false,
            form: {
                name: "Nouveau site",
                language: "fr",
                sector: "",
                tone: "",
                inspiration: "",
                personas: "",
                objectives: "",
                pages_wanted: "",
                set_as_homepage: true,
            },
            chatInput: "",
        });
        onMounted(() => this.load());
    }

    get briefId() {
        return this.state.data && this.state.data.id;
    }

    get isGenerated() {
        return this.state.data && this.state.data.state === "generated";
    }

    get generateLabel() {
        return this.isGenerated ? "Mettre à jour le site" : "Générer le site";
    }

    get hasSite() {
        return this.isGenerated || this.isPublished;
    }

    get previewUrl() {
        // URL de la page d'accueil générée pour l'aperçu intégré (iframe).
        const url = this.state.data && this.state.data.homepage_url;
        return this.hasSite && url ? url : "";
    }

    get pages() {
        return (this.state.data && this.state.data.pages) || [];
    }

    get palette() {
        const p = this.state.data && this.state.data.palette;
        return p && typeof p === "object" ? p : {};
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    toggleProjects() {
        this.state.projectsOpen = !this.state.projectsOpen;
    }

    useSuggestion(text) {
        this.state.chatInput = text;
    }

    _applyPayload(payload) {
        this.state.data = payload;
        for (const f of FORM_FIELDS) {
            if (payload[f] !== undefined && payload[f] !== null) {
                this.state.form[f] = payload[f];
            }
        }
    }

    async load() {
        this.state.loading = true;
        try {
            const payload = await this.orm.call(
                "doorway.site.brief",
                "get_or_create_session",
                []
            );
            this._applyPayload(payload);
        } catch (err) {
            console.error(err);
            this.notification.add("Impossible de charger le Site Builder.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    _formVals() {
        const vals = {};
        for (const f of FORM_FIELDS) {
            vals[f] = this.state.form[f];
        }
        return vals;
    }

    async saveBrief() {
        if (!this.briefId) {
            return;
        }
        try {
            const payload = await this.orm.call("doorway.site.brief", "update_brief", [
                this.briefId,
                this._formVals(),
            ]);
            this._applyPayload(payload);
        } catch (err) {
            console.error(err);
            this.notification.add("Échec de l'enregistrement du brief.", {
                type: "warning",
            });
        }
    }

    async sendMessage() {
        const body = (this.state.chatInput || "").trim();
        if (!body || !this.briefId) {
            return;
        }
        this.state.chatInput = "";
        try {
            const payload = await this.orm.call("doorway.site.brief", "post_message", [
                this.briefId,
                body,
            ]);
            this._applyPayload(payload);
        } catch (err) {
            console.error(err);
            this.notification.add("Message non envoyé.", { type: "warning" });
        }
    }

    async generate() {
        if (!this.briefId || this.state.generating) {
            return;
        }
        this.state.generating = true;
        // L'éventuelle saisie sert d'instruction d'itération si un site existe.
        const instruction = this.isGenerated ? (this.state.chatInput || "").trim() : "";
        try {
            await this.saveBrief();
            const payload = await this.orm.call("doorway.site.brief", "generate", [
                this.briefId,
                instruction,
            ]);
            this._applyPayload(payload);
            this.state.chatInput = "";
            if (payload.state === "generated") {
                this.notification.add(payload.message || "Site généré.", {
                    type: "success",
                });
            } else if (payload.state === "error") {
                this.notification.add(payload.last_error || "Génération en échec.", {
                    type: "danger",
                });
            }
        } catch (err) {
            console.error(err);
            this.notification.add("La génération a échoué.", { type: "danger" });
        } finally {
            this.state.generating = false;
        }
    }

    get isPublished() {
        return this.state.data && this.state.data.state === "published";
    }

    get publishLabel() {
        if (this.isPublished) {
            return "Republier le site";
        }
        const cost = this.state.data && this.state.data.publish_cost;
        return cost ? `Publier le site (${cost} crédit${cost > 1 ? "s" : ""})` : "Publier le site";
    }

    async publish() {
        if (!this.briefId || this.state.publishing) {
            return;
        }
        this.state.publishing = true;
        try {
            const payload = await this.orm.call("doorway.site.brief", "publish", [this.briefId]);
            // Solde insuffisant → ouvrir le paywall (achat d'un pack).
            if (payload && payload.paywall) {
                this._applyPayload(payload);
                await this.action.doAction(payload.paywall);
                return;
            }
            this._applyPayload(payload);
            if (payload && payload.published) {
                this.notification.add(_t("Site publié et mis en ligne."), { type: "success" });
            } else if (payload && payload.publish_error) {
                this.notification.add(payload.publish_error, { type: "danger" });
            }
        } catch (err) {
            console.error(err);
            this.notification.add(_t("La publication a échoué."), { type: "danger" });
        } finally {
            this.state.publishing = false;
        }
    }

    async newSession() {
        this.state.projectsOpen = false;
        try {
            const payload = await this.orm.call("doorway.site.brief", "create_session", []);
            this._applyPayload(payload);
            this.state.activeTab = "brief";
            this.notification.add("Nouveau projet créé.", { type: "info" });
        } catch (err) {
            console.error(err);
        }
    }

    openUrl(url) {
        if (url) {
            window.open(url, "_blank");
        }
    }

    openWebsite() {
        this.openUrl(this.state.data && this.state.data.homepage_url ? this.state.data.homepage_url : "/");
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}

registry.category("actions").add("doorway_site_builder_action", SiteBuilderApp);
