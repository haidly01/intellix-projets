/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const CPA_CLASS = {
    good: "cpa-good",
    warning: "cpa-warning",
    bad: "cpa-bad",
    neutral: "",
};

const ZONE_CLASS = {
    canada: "zone-ca",
    europe: "zone-eu",
    maroc: "zone-ma",
};

const RECO_CLASS = {
    urgent: "reco-urgent",
    opportunity: "reco-opportunity",
    info: "reco-info",
};

/** Retire les balises HTML des champs Odoo (optimization_summary, etc.). */
function stripHtml(value) {
    if (!value) return "";
    const text = String(value)
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<\/p>/gi, "\n")
        .replace(/<[^>]+>/g, "")
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .trim();
    return text.replace(/\n{3,}/g, "\n\n");
}

// ── Dashboard ─────────────────────────────────────────────────────────────

class TrafficDashboard extends Component {
    static template = "doorway_traffic_manager.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            stats: {},
            alerts: [],
            benchmarks: {},
        });
        onMounted(() => this._load());
    }

    async _load() {
        this.state.loading = true;
        this.state.stats = await this.orm.call(
            "doorway.traffic.campaign", "get_dashboard_stats", []
        );
        const alerts = await this.orm.call(
            "doorway.traffic.campaign", "get_dashboard_alerts", []
        );
        this.state.alerts = (alerts || []).map((a) => ({
            ...a,
            recommendation: stripHtml(a.recommendation),
        }));
        this.state.benchmarks = this.state.stats.benchmarks || {};
        this.state.loading = false;
    }

    plainText(value) {
        return stripHtml(value);
    }

    cpaClass(status) {
        return CPA_CLASS[status] || "";
    }

    recoClass(urgency) {
        return RECO_CLASS[urgency] || "reco-info";
    }

    openCampaign(id) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "traffic_campaigns_action",
            context: { default_campaign_id: id },
        });
    }

    openRecommendations() {
        this.action.doAction("doorway_traffic_manager.action_traffic_recommendations");
    }

    newCampaign() {
        this.action.doAction("doorway_traffic_manager.action_traffic_campaign_wizard");
    }
}

// ── Campagnes + drawer ──────────────────────────────────────────────────────

class TrafficCampaigns extends Component {
    static template = "doorway_traffic_manager.Campaigns";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            view: "list",
            campaigns: [],
            zones: [],
            filters: { zone: "", status: "" },
            drawerOpen: false,
            drawerLoading: false,
            drawerTab: "analyse",
            drawer: null,
        });
        onMounted(async () => {
            await this._load();
            const ctx = this.props.action?.context || {};
            if (ctx.default_campaign_id) {
                await this.openDrawer(ctx.default_campaign_id);
            }
        });
    }

    async _load() {
        this.state.loading = true;
        const data = await this.orm.call(
            "doorway.traffic.campaign",
            "dashboard_list_campaigns",
            [],
            { filters: this.state.filters }
        );
        this.state.campaigns = data.campaigns || [];
        this.state.zones = data.zones || [];
        this.state.loading = false;
    }

    setFilter(key, value) {
        this.state.filters[key] = value;
        this._load();
    }

    cpaClass(status) {
        return CPA_CLASS[status] || "";
    }

    zoneClass(zone) {
        return ZONE_CLASS[zone] || "";
    }

    async openDrawer(id) {
        this.state.drawerOpen = true;
        this.state.drawerLoading = true;
        this.state.drawerTab = "analyse";
        try {
            this.state.drawer = await this.orm.call(
                "doorway.traffic.campaign",
                "dashboard_campaign_detail",
                [[id]]
            );
        } catch (err) {
            this.notification.add(err.message || "Erreur", { type: "danger" });
        }
        this.state.drawerLoading = false;
    }

    closeDrawer() {
        this.state.drawerOpen = false;
        this.state.drawer = null;
    }

    setDrawerTab(tab) {
        this.state.drawerTab = tab;
    }

    async runAnalysis() {
        if (!this.state.drawer?.campaign?.id) return;
        this.state.drawerLoading = true;
        this.state.drawer = await this.orm.call(
            "doorway.traffic.campaign",
            "action_analyze_with_ai",
            [[this.state.drawer.campaign.id]]
        );
        this.state.drawerLoading = false;
        this.notification.add("Analyse IA terminée.", { type: "success" });
    }

    async applyReco(recoId) {
        await this.orm.call("doorway.traffic.campaign.reco", "action_apply", [[recoId]]);
        await this.openDrawer(this.state.drawer.campaign.id);
        await this._load();
        this.notification.add("Recommandation appliquée.", { type: "success" });
    }

    async generateAudience() {
        const id = this.state.drawer?.campaign?.id;
        if (!id) return;
        await this.orm.call("doorway.traffic.campaign", "action_suggest_audience", [[id]]);
        await this.openDrawer(id);
        this.notification.add("Audiences générées.", { type: "success" });
    }

    async generateCanva() {
        const id = this.state.drawer?.campaign?.id;
        if (!id) return;
        const res = await this.orm.call(
            "doorway.traffic.campaign", "action_generate_canva_creative", [[id]]
        );
        await this.openDrawer(id);
        this._notifyMediaResult(res, "Visuel Canva généré.");
    }

    _notifyMediaResult(res, successLabel) {
        const msg = res?.message;
        if (msg) {
            this.notification.add(msg, {
                type: res?.status === "placeholder" ? "warning" : "info",
            });
        } else {
            this.notification.add(successLabel, { type: "success" });
        }
    }

    async generateHeygen() {
        const id = this.state.drawer?.campaign?.id;
        if (!id) return;
        await this.orm.call("doorway.traffic.campaign", "action_generate_heygen_video", [[id]]);
        await this.openDrawer(id);
        this.notification.add("Vidéo HeyGen lancée.", { type: "success" });
    }

    newCampaign() {
        this.action.doAction("doorway_traffic_manager.action_traffic_campaign_wizard");
    }
}

// ── Inbox recommandations ───────────────────────────────────────────────────

class TrafficRecoInbox extends Component {
    static template = "doorway_traffic_manager.RecoInbox";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            pending_count: 0,
            applied_month: 0,
            recos: [],
        });
        onMounted(() => this._load());
    }

    async _load() {
        this.state.loading = true;
        const data = await this.orm.call(
            "doorway.traffic.campaign.reco", "get_inbox_data", []
        );
        this.state.recos = (data.recos || []).map((r) => ({
            ...r,
            body: stripHtml(r.body),
        }));
        this.state.pending_count = data.pending_count;
        this.state.applied_month = data.applied_month;
        this.state.loading = false;
    }

    recoClass(urgency) {
        return RECO_CLASS[urgency] || "reco-info";
    }

    async applyReco(id) {
        await this.orm.call("doorway.traffic.campaign.reco", "action_apply", [[id]]);
        await this._load();
        this.notification.add("Recommandation appliquée.", { type: "success" });
    }

    async ignoreReco(id) {
        await this.orm.call("doorway.traffic.campaign.reco", "action_ignore", [[id]]);
        await this._load();
    }

    async analyzeAll() {
        this.state.loading = true;
        await this.orm.call("doorway.traffic.campaign.reco", "analyze_all_campaigns", []);
        await this._load();
        this.notification.add("Analyse globale terminée.", { type: "success" });
    }
}

// ── Grille créatifs ─────────────────────────────────────────────────────────

class TrafficCreativeGrid extends Component {
    static template = "doorway_traffic_manager.CreativeGrid";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            creatives: [],
            filters: { format: "", status: "" },
            editOpen: false,
            editLoading: false,
            creative: null,
            suggestions: [],
        });
        onMounted(() => this._load());
    }

    async _load() {
        this.state.loading = true;
        const data = await this.orm.call(
            "doorway.creative",
            "get_creatives_grid",
            [],
            { filters: this.state.filters }
        );
        this.state.creatives = data.creatives || [];
        this.state.loading = false;
    }

    setFilter(key, value) {
        this.state.filters[key] = value;
        this._load();
    }

    imageUrl(id) {
        return `/web/image/doorway.creative/${id}/preview_image`;
    }

    statusBadge(status) {
        const map = {
            winner: "GAGNANT",
            active: "ACTIF",
            approved: "EN TEST",
            proposed: "EN TEST",
            loser: "PERDANT",
        };
        return map[status] || status;
    }

    async openEdit(c) {
        this.state.editOpen = true;
        this.state.editLoading = true;
        const rows = await this.orm.read("doorway.creative", [c.id], [
            "headline", "body", "cta", "format", "campaign_id",
        ]);
        this.state.creative = rows[0] || {};
        this.state.suggestions = [];
        this.state.editLoading = false;
    }

    closeEdit() {
        this.state.editOpen = false;
        this.state.creative = null;
    }

    async loadSuggestions() {
        if (!this.state.creative?.id) return;
        this.state.suggestions = await this.orm.call(
            "doorway.creative",
            "action_get_ai_suggestions",
            [[this.state.creative.id]]
        );
    }

    applySuggestion(text) {
        if (this.state.creative) {
            this.state.creative.headline = text;
        }
    }

    async saveCreative() {
        const c = this.state.creative;
        if (!c?.id) return;
        await this.orm.write("doorway.creative", [c.id], {
            headline: c.headline,
            body: c.body,
            cta: c.cta,
        });
        this.closeEdit();
        await this._load();
        this.notification.add("Créatif enregistré.", { type: "success" });
    }

    async generateCanva(id) {
        const res = await this.orm.call(
            "doorway.creative", "action_generate_canva_design", [[id]]
        );
        await this._load();
        if (res?.message) {
            this.notification.add(res.message, {
                type: res.status === "placeholder" ? "warning" : "info",
            });
        } else {
            this.notification.add("Canva généré.", { type: "success" });
        }
    }

    async generateHeygen(id) {
        await this.orm.call("doorway.creative", "action_generate_video", [[id]]);
        await this._load();
        this.notification.add("HeyGen lancé.", { type: "success" });
    }
}

// ── Wizard création campagne ────────────────────────────────────────────────

const WIZARD_STEPS = [
    { id: 1, label: "Canal" },
    { id: 2, label: "Zone" },
    { id: 3, label: "Brief" },
    { id: 4, label: "Audiences" },
    { id: 5, label: "Créatifs" },
];

class TrafficCampaignWizard extends Component {
    static template = "doorway_traffic_manager.CampaignWizard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.steps = WIZARD_STEPS;
        this.state = useState({
            loading: true,
            step: 1,
            channels: [],
            foundations: [],
            zones: [],
            channelCode: "",
            zone: "",
            foundationId: null,
            budgetDaily: 50,
            campaignName: "",
            briefSummary: "",
            messages: [],
            chatInput: "",
            chatReady: false,
            briefChecklist: {},
            chatTurn: 0,
            briefStarted: false,
            audiences: [],
            creatives: [],
            strategyNotes: "",
            generating: false,
        });
        onMounted(() => this._init());
    }

    async _init() {
        this.state.loading = true;
        const data = await this.orm.call(
            "doorway.traffic.campaign.wizard", "wizard_get_init", []
        );
        this.state.channels = data.channels || [];
        this.state.foundations = data.foundations || [];
        this.state.zones = data.zones || [];
        this.state.loading = false;
    }

    zoneClass(zone) {
        return ZONE_CLASS[zone] || "";
    }

    channelLabel(code) {
        const ch = this.state.channels.find((c) => c.code === code);
        return ch ? ch.name : code;
    }

    zoneLabel(code) {
        const z = this.state.zones.find((z) => z.code === code);
        return z ? z.label : code;
    }

    targetCpa() {
        const z = this.state.zones.find((z) => z.code === this.state.zone);
        return z ? `${z.target_cpa} ${z.currency}` : "—";
    }

    selectChannel(code) {
        this.state.channelCode = code;
    }

    selectZone(code) {
        this.state.zone = code;
    }

    selectFoundation(id) {
        this.state.foundationId = id;
        const f = this.state.foundations.find((x) => x.id === id);
        if (f && f.zone && !this.state.zone) {
            this.state.zone = f.zone;
        }
    }

    onBudgetInput(ev) {
        this.state.budgetDaily = parseFloat(ev.target.value) || 0;
    }

    onNameInput(ev) {
        this.state.campaignName = ev.target.value;
    }

    onChatInput(ev) {
        this.state.chatInput = ev.target.value;
    }

    canNext() {
        const s = this.state;
        if (s.step === 1) return !!s.channelCode;
        if (s.step === 2) return !!s.zone && !!s.foundationId;
        if (s.step === 3) {
            return s.chatReady && !!s.briefSummary;
        }
        if (s.step === 4) return s.audiences.some((a) => a.accepted);
        return s.creatives.some((c) => c.accepted);
    }

    async prevStep() {
        if (this.state.step > 1) {
            this.state.step -= 1;
        }
    }

    async nextStep() {
        if (!this.canNext()) return;
        if (this.state.step === 3) {
            await this._generateProposals();
            return;
        }
        if (this.state.step === 2) {
            this.state.step = 3;
            await this.startBrief();
            return;
        }
        if (this.state.step < 5) {
            this.state.step += 1;
            if (this.state.step === 5) {
                await this._enrichCreativePreviews();
            }
        }
    }

    async startBrief() {
        if (this.state.briefStarted) return;
        this.state.briefStarted = true;
        this.state.generating = true;
        try {
            const res = await this.orm.call(
                "doorway.traffic.campaign.wizard",
                "wizard_chat_start",
                [],
                {
                    foundation_id: this.state.foundationId,
                    channel_code: this.state.channelCode,
                    zone: this.state.zone,
                    budget_daily: this.state.budgetDaily,
                }
            );
            this.state.messages.push({ role: "assistant", text: res.reply || "" });
            this.state.briefChecklist = res.checklist || {};
            this.state.chatTurn = res.turn || 1;
            this.state.chatReady = !!res.ready;
            if (res.campaign_name) this.state.campaignName = res.campaign_name;
            if (res.budget_daily_suggested) this.state.budgetDaily = res.budget_daily_suggested;
            if (res.summary) this.state.briefSummary = res.summary;
        } catch (err) {
            this.notification.add(err.message || "Erreur démarrage brief", { type: "danger" });
        }
        this.state.generating = false;
    }

    checklistDone(key) {
        return !!this.state.briefChecklist[key];
    }

    isVideoFormat(fmt) {
        return ["video", "reel", "story"].includes(fmt || "");
    }

    async sendChat() {
        const text = (this.state.chatInput || "").trim();
        if (!text) return;
        this.state.messages.push({ role: "user", text });
        this.state.chatInput = "";
        this.state.generating = true;
        try {
            const res = await this.orm.call(
                "doorway.traffic.campaign.wizard",
                "wizard_chat",
                [],
                {
                    foundation_id: this.state.foundationId,
                    channel_code: this.state.channelCode,
                    zone: this.state.zone,
                    message: text,
                    history: this.state.messages,
                    budget_daily: this.state.budgetDaily,
                }
            );
            this.state.messages.push({ role: "assistant", text: res.reply || "" });
            if (res.campaign_name) {
                this.state.campaignName = res.campaign_name;
            }
            if (res.budget_daily_suggested) {
                this.state.budgetDaily = res.budget_daily_suggested;
            }
            if (res.summary) {
                this.state.briefSummary = res.summary;
            }
            this.state.briefChecklist = res.checklist || this.state.briefChecklist;
            this.state.chatTurn = res.turn || this.state.chatTurn + 1;
            this.state.chatReady = !!res.ready;
        } catch (err) {
            this.notification.add(err.message || "Erreur Claude", { type: "danger" });
        }
        this.state.generating = false;
    }

    async _generateProposals() {
        this.state.generating = true;
        try {
            const data = await this.orm.call(
                "doorway.traffic.campaign.wizard",
                "wizard_generate",
                [],
                {
                    foundation_id: this.state.foundationId,
                    channel_code: this.state.channelCode,
                    zone: this.state.zone,
                    brief_summary: this.state.briefSummary,
                    budget_daily: this.state.budgetDaily,
                    campaign_name: this.state.campaignName,
                }
            );
            this.state.audiences = data.audiences || [];
            this.state.creatives = data.creatives || [];
            this.state.strategyNotes = data.strategy_notes || "";
            this.state.step = 4;
        } catch (err) {
            this.notification.add(err.message || "Génération échouée", { type: "danger" });
        }
        this.state.generating = false;
    }

    toggleAudience(index) {
        const a = this.state.audiences[index];
        if (a) a.accepted = !a.accepted;
    }

    toggleCreative(index) {
        const c = this.state.creatives[index];
        if (c) c.accepted = !c.accepted;
    }

    async _enrichCreativePreviews() {
        for (const cr of this.state.creatives) {
            if (!cr.preview_url && cr.headline) {
                cr.preview_url = null;
            }
        }
    }

    async generateCreativeMedia(index) {
        const cr = this.state.creatives[index];
        if (!cr) return;
        cr.generating_media = true;
        try {
            const method = this.isVideoFormat(cr.format)
                ? "wizard_generate_heygen"
                : "wizard_generate_canva";
            const res = await this.orm.call(
                "doorway.traffic.campaign.wizard",
                method,
                [],
                { foundation_id: this.state.foundationId, creative: cr }
            );
            Object.assign(cr, res);
            if (res.message) {
                this.notification.add(res.message, {
                    type: res.media_status === "placeholder" ? "warning" : "info",
                });
            } else {
                this.notification.add("Média généré.", { type: "success" });
            }
        } catch (err) {
            this.notification.add(err.message || "Génération média échouée", {
                type: "danger",
            });
        }
        cr.generating_media = false;
    }

    async generateAllMedia() {
        this.state.generating = true;
        try {
            const data = await this.orm.call(
                "doorway.traffic.campaign.wizard",
                "wizard_generate_all_media",
                [],
                {
                    foundation_id: this.state.foundationId,
                    creatives: this.state.creatives,
                }
            );
            this.state.creatives = data.creatives || this.state.creatives;
            const ok = (data.results || []).filter((r) => r.ok).length;
            this.notification.add(`${ok} média(s) généré(s).`, { type: "success" });
        } catch (err) {
            this.notification.add(err.message || "Erreur", { type: "danger" });
        }
        this.state.generating = false;
    }

    openCanva(cr) {
        if (cr.canva_design_url) {
            window.open(cr.canva_design_url, "_blank");
        }
    }

    async launchCampaign() {
        if (!this.canNext()) return;
        this.state.generating = true;
        try {
            const res = await this.orm.call(
                "doorway.traffic.campaign.wizard",
                "wizard_create",
                [],
                {
                    foundation_id: this.state.foundationId,
                    channel_code: this.state.channelCode,
                    zone: this.state.zone,
                    brief_summary: this.state.briefSummary,
                    budget_daily: this.state.budgetDaily,
                    campaign_name: this.state.campaignName,
                    audiences: this.state.audiences,
                    creatives: this.state.creatives,
                }
            );
            this.notification.add(
                `Campagne « ${res.campaign_name} » créée — validez les propositions IA.`,
                { type: "success" }
            );
            this.action.doAction({
                type: "ir.actions.client",
                tag: "traffic_campaigns_action",
                context: { default_campaign_id: res.campaign_id },
            });
        } catch (err) {
            this.notification.add(err.message || "Création échouée", { type: "danger" });
        }
        this.state.generating = false;
    }

    cancel() {
        this.action.doAction("doorway_traffic_manager.action_traffic_dashboard");
    }

    stepClass(stepId) {
        if (this.state.step === stepId) return "active";
        if (this.state.step > stepId) return "done";
        return "";
    }
}

// ── Paramètres ──────────────────────────────────────────────────────────────

class TrafficSettings extends Component {
    static template = "doorway_traffic_manager.Settings";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            saving: false,
            canva_mcp_url: "",
            heygen_api_key: "",
            canva_configured: false,
            heygen_configured: false,
        });
        onMounted(() => this._load());
    }

    async _load() {
        this.state.loading = true;
        const data = await this.orm.call(
            "doorway.traffic.campaign.wizard", "get_integration_settings", []
        );
        this.state.canva_mcp_url = data.canva_mcp_url || "";
        this.state.heygen_api_key = data.heygen_api_key || "";
        this.state.canva_configured = data.canva_configured;
        this.state.heygen_configured = data.heygen_configured;
        this.state.loading = false;
    }

    async saveIntegrations() {
        this.state.saving = true;
        const data = await this.orm.call(
            "doorway.traffic.campaign.wizard",
            "save_integration_settings",
            [],
            {
                canva_mcp_url: this.state.canva_mcp_url,
                heygen_api_key: this.state.heygen_api_key,
            }
        );
        this.state.canva_configured = data.canva_configured;
        this.state.heygen_configured = data.heygen_configured;
        this.state.saving = false;
        this.notification.add("Intégrations enregistrées.", { type: "success" });
    }

    openBrandFoundations() {
        this.action.doAction("doorway_traffic_manager.action_brand_foundation");
    }

    openSystemSettings() {
        this.action.doAction("base.action_res_config_settings");
    }
}

registry.category("actions").add("traffic_dashboard_action", TrafficDashboard);
registry.category("actions").add("traffic_campaigns_action", TrafficCampaigns);
registry.category("actions").add("traffic_recommendations_action", TrafficRecoInbox);
registry.category("actions").add("traffic_creatives_action", TrafficCreativeGrid);
registry.category("actions").add("traffic_settings_action", TrafficSettings);
registry.category("actions").add("traffic_campaign_wizard_action", TrafficCampaignWizard);
