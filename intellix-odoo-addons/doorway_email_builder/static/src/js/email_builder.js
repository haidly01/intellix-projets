/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const FORM_FIELDS = [
    "name",
    "language",
    "brand",
    "objective",
    "persona",
    "tone",
    "offer",
    "cta",
    "sequence_length",
    "create_campaigns",
];

export class EmailBuilderApp extends Component {
    static template = "doorway_email_builder.App";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            generating: false,
            publishing: false,
            data: null,
            form: {
                name: "Nouvelle campagne email",
                language: "fr",
                brand: "",
                objective: "",
                persona: "",
                tone: "",
                offer: "",
                cta: "",
                sequence_length: 1,
                create_campaigns: true,
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
        return this.isGenerated ? "Mettre à jour" : "Générer l'email";
    }

    get previewEmails() {
        return (this.state.data && this.state.data.emails) || [];
    }

    setSequence(n) {
        const val = Math.max(1, Math.min(parseInt(n, 10) || 1, 5));
        this.state.form.sequence_length = val;
        this.saveBrief();
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
                "doorway.email.brief",
                "get_or_create_session",
                []
            );
            this._applyPayload(payload);
        } catch (err) {
            console.error(err);
            this.notification.add("Impossible de charger l'Email Builder.", {
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
        vals.sequence_length = parseInt(vals.sequence_length, 10) || 1;
        return vals;
    }

    async saveBrief() {
        if (!this.briefId) {
            return;
        }
        try {
            const payload = await this.orm.call("doorway.email.brief", "update_brief", [
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
            const payload = await this.orm.call("doorway.email.brief", "post_message", [
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
        // L'éventuelle saisie sert d'instruction d'itération si un email existe.
        const instruction = this.isGenerated ? (this.state.chatInput || "").trim() : "";
        try {
            await this.saveBrief();
            const payload = await this.orm.call("doorway.email.brief", "generate", [
                this.briefId,
                instruction,
            ]);
            this._applyPayload(payload);
            this.state.chatInput = "";
            if (payload.state === "generated") {
                this.notification.add("Email(s) généré(s).", { type: "success" });
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

    async newSession() {
        try {
            const payload = await this.orm.call("doorway.email.brief", "create_session", []);
            this._applyPayload(payload);
            this.notification.add("Nouvelle campagne créée.", { type: "info" });
        } catch (err) {
            console.error(err);
        }
    }

    get isSent() {
        return this.state.data && this.state.data.state === "sent";
    }

    get publishLabel() {
        if (this.isSent) {
            return "Renvoyer";
        }
        const cost = this.state.data && this.state.data.send_cost;
        return cost ? `Envoyer (${cost} crédit${cost > 1 ? "s" : ""})` : "Envoyer la campagne";
    }

    async publish() {
        if (!this.briefId || this.state.publishing) {
            return;
        }
        this.state.publishing = true;
        try {
            const payload = await this.orm.call("doorway.email.brief", "publish", [this.briefId]);
            if (payload && payload.paywall) {
                this._applyPayload(payload);
                await this.action.doAction(payload.paywall);
                return;
            }
            this._applyPayload(payload);
            if (payload && payload.sent) {
                this.notification.add(_t("Campagne mise en file d'envoi."), { type: "success" });
            } else if (payload && payload.publish_error) {
                this.notification.add(payload.publish_error, { type: "danger" });
            }
        } catch (err) {
            console.error(err);
            this.notification.add(_t("L'envoi a échoué."), { type: "danger" });
        } finally {
            this.state.publishing = false;
        }
    }

    async openMailings() {
        if (!this.briefId) {
            return;
        }
        try {
            const action = await this.orm.call(
                "doorway.email.brief",
                "action_open_mailing",
                [this.briefId]
            );
            await this.action.doAction(action);
        } catch (err) {
            console.error(err);
            this.notification.add("Impossible d'ouvrir les emails.", { type: "warning" });
        }
    }

    async openRecord(model, resId) {
        if (!resId) {
            return;
        }
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: model,
                res_id: resId,
                views: [[false, "form"]],
                target: "current",
            });
        } catch (err) {
            console.error(err);
            this.notification.add("Ouverture impossible.", { type: "warning" });
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}

registry.category("actions").add("doorway_email_builder_action", EmailBuilderApp);
