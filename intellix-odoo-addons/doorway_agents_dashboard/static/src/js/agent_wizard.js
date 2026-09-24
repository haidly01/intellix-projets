/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpcErrorMessage } from "./rpc_error";

const STEP_DEFS = [
    { id: "identity", label: "Identité" },
    { id: "voice", label: "Voix" },
    { id: "latency", label: "Latence" },
    { id: "prompt", label: "Prompt" },
    { id: "actions", label: "Actions" },
    { id: "library", label: "Bibliothèque" },
    { id: "telephony", label: "Téléphonie" },
    { id: "summary", label: "Récap" },
];

const STEP_ORDER = STEP_DEFS.map((s) => s.id);

class AgentWizard extends Component {
    static template = "doorway_agents_dashboard.AgentWizard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.steps = STEP_DEFS;
        this.state = useState({
            loading: true,
            agentId: null,
            currentStep: "identity",
            completionPct: 0,
            form: {
                name: "",
                pipeline: "doorway",
                agent_type: "inbound",
                language: "fr",
                voice_id: "",
                voice_name: "",
                voice_gender: "female",
                voice_locale: "",
                voice_clone_id: "",
                export_calls_google_sheet: false,
                google_sheets_spreadsheet_id: "",
                has_voice_sample: false,
                voice_sample_filename: "",
                voice_speed: 1.0,
                voice_stability: 0.5,
                latency_mode: "balanced",
                system_prompt: "",
                action_tag_ids: [],
                n8n_webhook_url: "",
                is_template: false,
                template_name: "",
                template_tag_ids: [],
            },
            pipelines: [],
            latencyModes: [],
            variables: [],
            actions: [],
            voices: [],
            templates: [],
            testPhone: "",
            showPromptModal: false,
            promptTestMessage: "Bonjour, je voudrais des informations.",
            promptTestReply: "",
            promptSource: "own",
            promptLinkedName: "",
            deploying: false,
            voiceCloning: false,
            audio: null,
            isEditMode: false,
            telephonyMode: "existing",
            telephony: {
                phone_number: "",
                phone_source: "manual",
                sip_trunk_name: "",
                twilio_sip_trunk_sid: "",
                trunk_id: false,
                elevenlabs_phone_number_id: "",
            },
            twilioConfigured: false,
            twilioOwnedNumbers: [],
            twilioSearchResults: [],
            searchCountry: "CA",
            searchAreaCode: "",
            sipTrunks: [],
            phoneInput: "",
            trunkForm: {
                name: "",
                provider: "custom",
                twilio_trunk_sid: "",
                termination_uri: "",
            },
            assigningPhone: false,
            searchingNumbers: false,
        });
        onMounted(() => this.initWizard());
    }

    onFormInput(ev) {
        const field = ev.target.dataset.field;
        if (!field) {
            return;
        }
        let value = ev.target.value;
        if (ev.target.type === "checkbox") {
            value = ev.target.checked;
        } else if (ev.target.type === "range") {
            value = parseFloat(ev.target.value);
        }
        this.updateForm(field, value);
        if (field === "system_prompt") {
            this.state.promptSource = "own";
        }
    }

    onVoiceGenderChange(ev) {
        this.updateForm("voice_gender", ev.target.value);
        this.loadVoices();
    }

    onVoiceLocaleChange(ev) {
        this.updateForm("voice_locale", ev.target.value);
        this.loadVoices();
    }

    onActionToggle(ev) {
        const actionId = parseInt(ev.target.dataset.actionId, 10);
        this.toggleAction(actionId, ev.target.checked);
    }

    onTestPhoneInput(ev) {
        this.state.testPhone = ev.target.value;
    }

    onPhoneInput(ev) {
        this.state.phoneInput = ev.target.value;
    }

    onTelephonyModeChange(ev) {
        this.state.telephonyMode = ev.target.value;
    }

    onSearchCountryChange(ev) {
        this.state.searchCountry = ev.target.value;
    }

    onSearchAreaCodeInput(ev) {
        this.state.searchAreaCode = ev.target.value;
    }

    onTrunkFormInput(ev) {
        const field = ev.target.dataset.trunkField;
        if (field) {
            this.state.trunkForm[field] = ev.target.value;
        }
    }

    onSelectTwilioOwnedClick(ev) {
        const phone = ev.currentTarget.dataset.phone;
        const sid = ev.currentTarget.dataset.sid || "";
        if (phone) {
            this.state.phoneInput = phone;
            this.state.telephony.twilio_incoming_sid = sid;
        }
    }

    onSelectTwilioSearchClick(ev) {
        const phone = ev.currentTarget.dataset.phone;
        if (phone) {
            this.state.phoneInput = phone;
        }
    }

    onSipTrunkSelectChange(ev) {
        const trunkId = parseInt(ev.target.value, 10) || false;
        this.state.telephony.trunk_id = trunkId;
    }

    onPromptTestMessageInput(ev) {
        this.state.promptTestMessage = ev.target.value;
    }

    onLatencyModeClick(ev) {
        const mode = ev.currentTarget.dataset.latencyMode;
        if (mode) {
            this.updateForm("latency_mode", mode);
        }
    }

    onInsertVariableClick(ev) {
        const token = ev.currentTarget.dataset.token;
        if (token) {
            this.insertVariable(token);
        }
    }

    onLoadTemplateClick(ev) {
        const templateId = parseInt(ev.currentTarget.dataset.templateId, 10);
        if (templateId) {
            this.loadTemplate(templateId);
        }
    }

    onGoToStepClick(ev) {
        const stepId = ev.currentTarget.dataset.stepId;
        if (stepId) {
            this.goToStep(stepId);
        }
    }

    onSelectVoiceClick(ev) {
        const card = ev.currentTarget;
        const voiceId = card.dataset.voiceId;
        if (!voiceId) {
            return;
        }
        const voice = this.state.voices.find((v) => v.voice_id === voiceId);
        this.selectVoice(voiceId, voice);
    }

    onPlayVoiceClick(ev) {
        ev.stopPropagation();
        const voiceId = ev.currentTarget.dataset.voiceId;
        if (voiceId) {
            this.playVoice(voiceId);
        }
    }

    async initWizard() {
        try {
            const ctx = this.props.action?.context || {};
            let agentId = ctx.default_agent_id || ctx.active_id || null;
            if (!agentId) {
                agentId = await this.orm.call(
                    "doorway.agent.profile",
                    "wizard_create_draft",
                    []
                );
            }
            this.state.agentId = agentId;
            const config = await this.orm.call(
                "doorway.agent.profile",
                "wizard_get_config",
                [agentId]
            );
            this.state.pipelines = config.pipelines || [];
            this.state.latencyModes = config.latency_modes || [];
            this.state.variables = config.variables || [];
            this.state.actions = config.actions || [];
            if (config.agent) {
                Object.assign(this.state.form, config.agent);
                this.state.promptSource = config.agent.prompt_source || "own";
                this.state.promptLinkedName = config.agent.prompt_linked_name || "";
                const forcedStep = ctx.open_wizard_step;
                this.state.currentStep = forcedStep || config.agent.wizard_step || "identity";
                this.state.completionPct = config.agent.wizard_completion_pct || 0;
                this.state.isEditMode = !!config.agent.is_edit_mode;
                if (config.agent.telephony) {
                    Object.assign(this.state.telephony, config.agent.telephony);
                    this.state.phoneInput = config.agent.telephony.phone_number || "";
                }
            }
            await this.loadVoices();
            await this.loadTemplates();
            if (this.state.currentStep === "telephony") {
                await this.loadTelephony();
            }
        } catch (err) {
            console.error(err);
            this.notification.add(rpcErrorMessage(err) || "Erreur initialisation wizard.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    async loadVoices() {
        if (!this.state.agentId) {
            return;
        }
        this.state.voices = await this.orm.call(
            "doorway.agent.profile",
            "wizard_list_voices",
            [
                [this.state.agentId],
                this.state.form.language,
                this.state.form.voice_gender,
                this.state.form.voice_locale || false,
            ]
        );
    }

    async loadTemplates() {
        this.state.templates = await this.orm.call(
            "doorway.agent.profile",
            "wizard_list_templates",
            [this.state.form.pipeline]
        );
    }

    updateForm(key, value) {
        this.state.form[key] = value;
        if (key === "pipeline") {
            this.loadTemplates();
        }
        if (key === "language") {
            this.loadVoices();
        }
    }

    onVoiceFileChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.onload = async () => {
            try {
                const parts = String(reader.result || "").split(",");
                const b64 = parts.length > 1 ? parts[1] : parts[0];
                const res = await this.orm.call(
                    "doorway.agent.profile",
                    "wizard_upload_voice_sample",
                    [[this.state.agentId], file.name, b64]
                );
                this.state.form.has_voice_sample = res.has_voice_sample;
                this.state.form.voice_sample_filename = res.filename;
                this.notification.add("Échantillon audio enregistré.", { type: "success" });
            } catch (err) {
                this.notification.add(rpcErrorMessage(err) || "Upload audio échoué.", {
                    type: "danger",
                });
            }
        };
        reader.readAsDataURL(file);
    }

    async onCreateVoiceClone() {
        const voiceName =
            this.state.form.voice_name || this.state.form.name || "Ma voix";
        this.state.voiceCloning = true;
        try {
            const res = await this.orm.call(
                "doorway.agent.profile",
                "wizard_create_voice_clone",
                [[this.state.agentId], voiceName]
            );
            this.state.form.voice_id = res.voice_id;
            this.state.form.voice_clone_id = res.voice_id;
            this.state.form.voice_name = res.voice_name;
            this.state.voices = res.voices || [];
            await this.saveCurrentStep("voice");
            this.notification.add("Voix clonée et sélectionnée.", { type: "success" });
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Clonage voix échoué.", { type: "danger" });
        } finally {
            this.state.voiceCloning = false;
        }
    }

    get languageLabel() {
        const labels = {
            fr: "Français",
            en: "Anglais",
            es: "Español",
            bilingual: "Multilingue",
        };
        return labels[this.state.form.language] || this.state.form.language;
    }

    stepIndex(stepId) {
        return STEP_ORDER.indexOf(stepId);
    }

    isStepDone(stepId) {
        return this.stepIndex(stepId) < this.stepIndex(this.state.currentStep);
    }

    stepClass(step) {
        let cls = "ix-wiz-step";
        if (step.id === this.state.currentStep) {
            cls += " ix-wiz-step--active";
        } else if (this.isStepDone(step.id)) {
            cls += " ix-wiz-step--done";
        }
        return cls;
    }

    canJumpTo(stepId) {
        return this.stepIndex(stepId) <= this.stepIndex(this.state.currentStep);
    }

    get canGoBack() {
        return this.stepIndex(this.state.currentStep) > 0;
    }

    get latencyHint() {
        const mode = this.state.latencyModes.find(
            (m) => m.value === this.state.form.latency_mode
        );
        return mode ? mode.hint : "";
    }

    get tokenEstimate() {
        return Math.max(1, Math.round((this.state.form.system_prompt || "").length / 4));
    }

    get stabilityPercent() {
        return Math.round((this.state.form.voice_stability || 0) * 100);
    }

    get hasN8nAction() {
        const n8n = this.state.actions.find((a) => a.code === "n8n_workflow");
        return n8n && this.state.form.action_tag_ids.includes(n8n.id);
    }

    get selectedVoiceName() {
        const v = this.state.voices.find(
            (x) => x.voice_id === this.state.form.voice_id
        );
        return v ? v.name : this.state.form.voice_id || "—";
    }

    get voiceGenderLabel() {
        const labels = { female: "Femme", male: "Homme", any: "Toutes" };
        return labels[this.state.form.voice_gender] || "Femme";
    }

    voiceGenderIcon(gender) {
        if (gender === "male") {
            return "♂";
        }
        if (gender === "female") {
            return "♀";
        }
        return "";
    }

    get selectedActionsLabel() {
        const ids = new Set(this.state.form.action_tag_ids);
        const names = this.state.actions
            .filter((a) => ids.has(a.id))
            .map((a) => a.name);
        return names.length ? names.join(", ") : "Aucune";
    }

    isActionChecked(actionId) {
        return this.state.form.action_tag_ids.includes(actionId);
    }

    toggleAction(actionId, checked) {
        const ids = [...this.state.form.action_tag_ids];
        const idx = ids.indexOf(actionId);
        if (checked && idx < 0) {
            ids.push(actionId);
        } else if (!checked && idx >= 0) {
            ids.splice(idx, 1);
        }
        this.state.form.action_tag_ids = ids;
    }

    selectVoice(voiceId, voiceMeta = null) {
        this.updateForm("voice_id", voiceId);
        if (voiceMeta && voiceMeta.name) {
            this.updateForm("voice_name", voiceMeta.name);
        }
    }

    async playVoice(voiceId) {
        try {
            const res = await this.orm.call(
                "doorway.agent.profile",
                "wizard_voice_preview",
                [[this.state.agentId]],
                {
                    voice_id: voiceId,
                    speed: this.state.form.voice_speed,
                    stability: this.state.form.voice_stability,
                    language: this.state.form.language,
                }
            );
            if (this.state.audio) {
                this.state.audio.pause();
            }
            const audio = new Audio(
                `data:${res.mime};base64,${res.audio_base64}`
            );
            this.state.audio = audio;
            await audio.play();
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Aperçu voix impossible.", {
                type: "warning",
            });
        }
    }

    insertVariable(token) {
        this.state.form.system_prompt = (this.state.form.system_prompt || "") + token;
    }

    openPromptTest() {
        this.state.showPromptModal = true;
        this.state.promptTestReply = "";
    }

    closePromptTest() {
        this.state.showPromptModal = false;
    }

    async runPromptTest() {
        try {
            const res = await this.orm.call(
                "doorway.agent.profile",
                "wizard_test_prompt",
                [],
                {
                    system_prompt: this.state.form.system_prompt,
                    user_message: this.state.promptTestMessage,
                }
            );
            this.state.promptTestReply = res.reply || "(pas de réponse)";
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Test prompt échoué.", { type: "danger" });
        }
    }

    async saveCurrentStep(stepOverride) {
        const step = stepOverride || this.state.currentStep;
        const payload = { ...this.state.form };
        const saved = await this.orm.call(
            "doorway.agent.profile",
            "wizard_save_step",
            [[this.state.agentId], step, payload]
        );
        Object.assign(this.state.form, saved);
        this.state.completionPct = saved.wizard_completion_pct || 0;
    }

    get wizardTitle() {
        return this.state.isEditMode
            ? "Modification d'agent IA"
            : "Création d'agent IA";
    }

    get telephonySummary() {
        return this.state.telephony.phone_number || "Non assigné";
    }

    async loadTelephony() {
        if (!this.state.agentId) {
            return;
        }
        const data = await this.orm.call(
            "doorway.agent.profile",
            "wizard_get_telephony",
            [[this.state.agentId]]
        );
        if (data.telephony) {
            Object.assign(this.state.telephony, data.telephony);
            this.state.phoneInput = data.telephony.phone_number || "";
        }
        this.state.twilioConfigured = !!data.twilio_configured;
        this.state.twilioOwnedNumbers = data.twilio_owned_numbers || [];
        this.state.sipTrunks = data.sip_trunks || [];
    }

    async searchTwilioNumbers() {
        this.state.searchingNumbers = true;
        try {
            this.state.twilioSearchResults = await this.orm.call(
                "doorway.agent.profile",
                "wizard_search_twilio_numbers",
                [],
                {
                    country: this.state.searchCountry,
                    area_code: this.state.searchAreaCode || null,
                }
            );
            if (!this.state.twilioSearchResults.length) {
                this.notification.add("Aucun numéro disponible pour cette recherche.", {
                    type: "warning",
                });
            }
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Recherche Twilio échouée.", {
                type: "danger",
            });
        } finally {
            this.state.searchingNumbers = false;
        }
    }

    async assignPhone() {
        const mode = this.state.telephonyMode;
        const payload = {
            phone_number: this.state.phoneInput,
            country_code: this.state.searchCountry,
            trunk_id: this.state.telephony.trunk_id || false,
            twilio_incoming_sid: this.state.telephony.twilio_incoming_sid || "",
            trunk_name: this.state.trunkForm.name,
            trunk_provider: this.state.trunkForm.provider,
            twilio_sip_trunk_sid: this.state.trunkForm.twilio_trunk_sid,
            termination_uri: this.state.trunkForm.termination_uri,
            sip_trunk_name: this.state.trunkForm.name,
        };
        if (!payload.phone_number) {
            this.notification.add("Entrez ou sélectionnez un numéro.", { type: "warning" });
            return;
        }
        this.state.assigningPhone = true;
        try {
            const result = await this.orm.call(
                "doorway.agent.profile",
                "wizard_assign_phone",
                [[this.state.agentId], mode, payload]
            );
            Object.assign(this.state.telephony, result);
            this.state.phoneInput = result.phone_number || "";
            await this.saveCurrentStep("telephony");
            this.notification.add("Numéro assigné à l'agent.", { type: "success" });
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Assignation échouée.", { type: "danger" });
        } finally {
            this.state.assigningPhone = false;
        }
    }

    async createSipTrunk() {
        if (!this.state.trunkForm.name) {
            this.notification.add("Nom du trunk requis.", { type: "warning" });
            return;
        }
        try {
            const res = await this.orm.call(
                "doorway.agent.profile",
                "wizard_create_sip_trunk",
                [[this.state.agentId], this.state.trunkForm]
            );
            this.state.sipTrunks = res.sip_trunks || [];
            this.state.telephony.trunk_id = res.trunk_id;
            this.notification.add("SIP trunk enregistré.", { type: "success" });
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Création trunk échouée.", { type: "danger" });
        }
    }

    async removePhone() {
        if (!this.state.telephony.phone_number) {
            return;
        }
        if (!window.confirm("Retirer le numéro assigné à cet agent ?")) {
            return;
        }
        try {
            const result = await this.orm.call(
                "doorway.agent.profile",
                "wizard_remove_phone",
                [[this.state.agentId]]
            );
            Object.assign(this.state.telephony, result);
            this.state.phoneInput = "";
            this.notification.add("Numéro retiré.", { type: "info" });
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Erreur.", { type: "danger" });
        }
    }

    async goNext() {
        const idx = this.stepIndex(this.state.currentStep);
        if (idx < 0 || idx >= STEP_ORDER.length - 1) {
            return;
        }
        await this.saveCurrentStep();
        this.state.currentStep = STEP_ORDER[idx + 1];
        await this.saveCurrentStep(this.state.currentStep);
        if (this.state.currentStep === "telephony") {
            await this.loadTelephony();
        }
    }

    async goBack() {
        const idx = this.stepIndex(this.state.currentStep);
        if (idx <= 0) {
            return;
        }
        await this.saveCurrentStep();
        this.state.currentStep = STEP_ORDER[idx - 1];
    }

    async goToStep(stepId) {
        if (!this.canJumpTo(stepId)) {
            return;
        }
        await this.saveCurrentStep();
        this.state.currentStep = stepId;
        if (stepId === "telephony") {
            await this.loadTelephony();
        }
    }

    async loadTemplate(templateId) {
        try {
            const newId = await this.orm.call(
                "doorway.agent.profile",
                "wizard_create_draft",
                [templateId]
            );
            this.state.agentId = newId;
            const config = await this.orm.call(
                "doorway.agent.profile",
                "wizard_get_config",
                [newId]
            );
            if (config.agent) {
                Object.assign(this.state.form, config.agent);
            }
            this.notification.add("Template chargé.", { type: "success" });
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Erreur template.", { type: "danger" });
        }
    }

    async deployAgent() {
        this.state.deploying = true;
        try {
            await this.saveCurrentStep("summary");
            const res = await this.orm.call(
                "doorway.agent.profile",
                "wizard_deploy",
                [[this.state.agentId]]
            );
            this.notification.add(
                `Agent déployé (${res.external_agent_id}).`,
                { type: "success" }
            );
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Déploiement échoué.", { type: "danger" });
        } finally {
            this.state.deploying = false;
        }
    }

    async startTestCall() {
        if (!this.state.testPhone) {
            this.notification.add("Entrez un numéro de téléphone.", { type: "warning" });
            return;
        }
        this.state.deploying = true;
        try {
            await this.saveCurrentStep("summary");
            const action = await this.orm.call(
                "doorway.agent.profile",
                "wizard_start_test_call",
                [[this.state.agentId], this.state.testPhone]
            );
            if (action) {
                this.action.doAction(action);
            }
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Appel test échoué.", { type: "danger" });
        } finally {
            this.state.deploying = false;
        }
    }

    async startWebTest(step = "summary") {
        if (!this.state.agentId) {
            this.notification.add("Enregistrez d'abord les étapes précédentes.", {
                type: "warning",
            });
            return;
        }
        this.state.deploying = true;
        try {
            await this.saveCurrentStep(step);
            const action = await this.orm.call(
                "doorway.agent.profile",
                "wizard_start_web_test",
                [[this.state.agentId]]
            );
            if (action) {
                this.action.doAction(action);
            }
        } catch (err) {
            this.notification.add(rpcErrorMessage(err) || "Test web indisponible.", {
                type: "danger",
            });
        } finally {
            this.state.deploying = false;
        }
    }

    async startWebTestFromPrompt() {
        if (!(this.state.form.system_prompt || "").trim()) {
            this.notification.add("Renseignez le prompt avant l'appel web.", {
                type: "warning",
            });
            return;
        }
        this.state.showPromptModal = false;
        await this.startWebTest("prompt");
    }
}

registry.category("actions").add("agent_wizard_action", AgentWizard);
