/** @odoo-module **/

import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { mountComponent } from "@web/env";

const TEMPLATES = {
    followup:
        "Bonjour {{prénom}} !\n\nMerci pour votre intérêt. Je suis disponible pour répondre à vos questions. Quel est le meilleur moment pour échanger ?",
    rdv: "Bonjour {{prénom}},\n\nVotre rendez-vous est confirmé pour le {{date}} à {{heure}}.\n\nÀ très bientôt !",
    devis:
        "Bonjour {{prénom}},\n\nVeuillez trouver ci-joint votre devis personnalisé.\n\nCordialement, {{agent}}",
    relance:
        "Bonjour {{prénom}},\n\nJe me permets de vous recontacter suite à notre dernier échange. Avez-vous pu examiner notre proposition ?",
};

const TEMPLATE_LABELS = {
    followup: "Suivi",
    rdv: "RDV",
    devis: "Devis",
    relance: "Relance",
};

const STEP_ITEMS = [
    { num: 1, label: "Composer" },
    { num: 2, label: "Canaux" },
    { num: 3, label: "Confirmer" },
];

export class WhatsAppWizard extends Component {
    static template = "doorway_messaging.WhatsAppWizard";
    static props = {
        record: Object,
        phone: { type: String, optional: true },
        recipientName: { type: String, optional: true },
        close: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.chatRef = useRef("chatScroll");

        const data = this.props.record?.data || {};
        this.state = useState({
            step: 1,
            message: data.message || "",
            waMessage: data.wa_message || data.message || "",
            smsMessage: data.sms_message || "",
            emailMessage: data.email_body || "",
            activeTab: "wa",
            timing: data.timing || "now",
            logCrm: data.log_crm !== false,
            relanceAuto: data.relance_auto || false,
            sending: false,
            sent: false,
            template: "",
        });

        this.chatHistory = useState([
            { dir: "in", text: "Bonjour, j'aimerais avoir plus d'infos.", time: "10:32" },
            { dir: "out", text: "Bien sûr, je vous recontacte !", time: "10:45", read: true },
        ]);

        this.stepItems = STEP_ITEMS;
        this.templateKeys = Object.keys(TEMPLATES);
        this.templateLabels = TEMPLATE_LABELS;
        this.composePlaceholder = _t("Écrivez votre message WhatsApp…");

        onPatched(() => this._scrollChat());
    }

    get recipientName() {
        return this.props.recipientName || _t("Contact");
    }

    get recipientInitial() {
        const name = this.recipientName || "?";
        return name.charAt(0).toUpperCase();
    }

    get confirmPreview() {
        const msg = this.state.waMessage || this.state.message || "";
        return msg.length > 80 ? msg.slice(0, 80) + "…" : msg;
    }

    stepClass(num) {
        if (num < this.state.step) return "done";
        if (num === this.state.step) return "active";
        return "idle";
    }

    stepNumClass(num) {
        if (num < this.state.step) return "done";
        if (num === this.state.step) return "active";
        return "idle";
    }

    stepLabelClass(num) {
        if (num < this.state.step) return "done";
        if (num === this.state.step) return "active";
        return "idle";
    }

    _scrollChat() {
        const el = this.chatRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    async _syncRecord(vals) {
        if (this.props.record?.update) {
            await this.props.record.update(vals);
        }
    }

    onMessageInput(ev) {
        this.state.message = ev.target.value;
        this._syncRecord({ message: this.state.message });
    }

    onWaMessageInput(ev) {
        this.state.waMessage = ev.target.value;
        this._syncRecord({ wa_message: this.state.waMessage });
    }

    onSmsMessageInput(ev) {
        this.state.smsMessage = ev.target.value;
        this._syncRecord({ sms_message: this.state.smsMessage });
    }

    onEmailMessageInput(ev) {
        this.state.emailMessage = ev.target.value;
        this._syncRecord({ email_body: this.state.emailMessage });
    }

    setActiveTab(tab) {
        this.state.activeTab = tab;
    }

    setTiming(timing) {
        this.state.timing = timing;
        this._syncRecord({ timing });
    }

    onLogCrmChange(ev) {
        this.state.logCrm = ev.target.checked;
        this._syncRecord({ log_crm: this.state.logCrm });
    }

    onRelanceChange(ev) {
        this.state.relanceAuto = ev.target.checked;
        this._syncRecord({ relance_auto: this.state.relanceAuto });
    }

    applyTemplate(key) {
        const tpl = TEMPLATES[key];
        if (!tpl) return;
        this.state.template = key;
        this.state.message = tpl;
        this.state.waMessage = tpl;
        this._syncRecord({ message: tpl, wa_message: tpl });
    }

    previewMessage() {
        if (!this.state.message.trim()) return;
        const now = new Date();
        this.chatHistory.push({
            dir: "out",
            text: this.state.message.trim(),
            time: `${now.getHours()}:${String(now.getMinutes()).padStart(2, "0")}`,
            read: false,
        });
        this.state.waMessage = this.state.message;
        this._syncRecord({ wa_message: this.state.waMessage });
        this.state.message = "";
        this._syncRecord({ message: "" });
        this._scrollChat();
    }

    insertVariable() {
        const vars = ["{{prénom}}", "{{date}}", "{{heure}}", "{{agent}}", "{{offre}}"];
        const v = vars[Math.floor(Math.random() * vars.length)];
        this.state.message += v;
        this._syncRecord({ message: this.state.message });
    }

    goNext() {
        if (this.state.step < 3) {
            if (this.state.step === 1) {
                if (this.state.message.trim()) {
                    this.state.waMessage = this.state.message;
                    this._syncRecord({ wa_message: this.state.waMessage, message: this.state.message });
                } else if (!this.state.waMessage.trim()) {
                    this.notification.add(_t("Veuillez saisir un message."), { type: "warning" });
                    return;
                }
            }
            if (this.state.step === 2 && !this.state.waMessage.trim()) {
                this.notification.add(_t("Le message WhatsApp est vide."), { type: "warning" });
                return;
            }
            this.state.step++;
        } else {
            this._doSend();
        }
    }

    goBack() {
        if (this.state.step > 1) {
            this.state.step--;
        }
    }

    async _doSend() {
        const resId = this.props.record?.resId;
        if (!resId) {
            this.notification.add(_t("Enregistrement wizard introuvable."), { type: "danger" });
            return;
        }
        this.state.sending = true;
        try {
            await this.orm.call(
                "doorway.whatsapp.send.wizard",
                "action_send",
                [[resId]],
                {
                    message: this.state.waMessage || this.state.message,
                    timing: this.state.timing,
                    log_crm: this.state.logCrm,
                    relance_auto: this.state.relanceAuto,
                }
            );
            this.state.step = 4;
            this.state.sent = true;
        } catch (e) {
            const msg = e?.data?.message || e?.message || String(e);
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.sending = false;
        }
    }

    async adaptWithClaude() {
        const msg = this.state.message.trim();
        if (!msg) {
            this.notification.add(_t("Saisissez un message à adapter."), { type: "warning" });
            return;
        }
        try {
            const res = await rpc("/doorway/claude/adapt_message", {
                message: msg,
                context: "whatsapp_lead_followup",
            });
            if (res.adapted) {
                this.state.message = res.adapted;
                this._syncRecord({ message: res.adapted });
                if (res.warning === "no_api_key") {
                    this.notification.add(_t("Clé Claude absente — adaptation locale."), {
                        type: "warning",
                    });
                }
            }
        } catch (e) {
            this.notification.add(_t("Erreur adaptation Claude."), { type: "danger" });
        }
    }

    resetWizard() {
        this.state.step = 1;
        this.state.message = "";
        this.state.waMessage = "";
        this.state.smsMessage = "";
        this.state.emailMessage = "";
        this.state.sent = false;
        this.state.template = "";
        this.state.timing = "now";
        this._syncRecord({
            message: "",
            wa_message: "",
            sms_message: "",
            email_body: "",
            timing: "now",
        });
    }

    onClose() {
        if (this.props.close) {
            this.props.close();
        }
    }
}

export class WhatsAppWizardFormController extends FormController {
    setup() {
        super.setup();
        this.actionService = useService("action");
        this._waMount = null;
        this._waApp = null;

        onMounted(() => this._mountWizard());
        onWillUnmount(() => this._unmountWizard());
    }

    _getMountEl() {
        return this.rootRef?.el?.querySelector?.(".wa-wizard-mount");
    }

    _getRecipientName() {
        const data = this.model?.root?.data || {};
        if (data.lead_id && data.lead_id[1]) {
            return data.lead_id[1];
        }
        if (data.partner_id && data.partner_id[1]) {
            return data.partner_id[1];
        }
        return _t("Contact");
    }

    async _mountWizard() {
        const el = this._getMountEl();
        if (!el || el.dataset.waMounted) {
            return;
        }
        el.dataset.waMounted = "1";

        const close = () => {
            this.actionService.doAction({ type: "ir.actions.act_window_close" });
        };

        this._waApp = await mountComponent(WhatsAppWizard, el, {
            env: this.env,
            props: {
                record: this.model.root,
                phone: this.model.root.data.phone || "",
                recipientName: this._getRecipientName(),
                close,
            },
            name: "WhatsAppWizard",
        });
        this._waMount = el;
    }

    _unmountWizard() {
        if (this._waApp) {
            this._waApp.destroy();
            this._waApp = null;
        }
        if (this._waMount) {
            delete this._waMount.dataset.waMounted;
            this._waMount = null;
        }
    }
}

export const whatsappWizardFormView = {
    ...formView,
    Controller: WhatsAppWizardFormController,
};

registry.category("views").add("whatsapp_wizard_form", whatsappWizardFormView);
