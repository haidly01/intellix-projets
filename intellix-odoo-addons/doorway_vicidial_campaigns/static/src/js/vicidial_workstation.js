/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const REFRESH_MS = 15000;
const REFRESH_MS_ACTIVE = 10000;
const HEARTBEAT_MS = 4000;
const CALL_TICK_MS = 1000;
const SEARCH_DEBOUNCE_MS = 300;
const MOBILE_MQ = "(max-width: 1200px)";
const COMPACT_MQ = "(max-width: 768px)";

class VicidialWorkstation extends Component {
    static template = "doorway_vicidial_campaigns.VicidialWorkstation";

    setup() {
        this.webphoneAllow = "microphone; autoplay";
        this.action = useService("action");
        this.notification = useService("notification");
        this.leadSync = useService("doorway_vicidial_lead_sync");
        this.state = useState({
            loading: true,
            agent: {},
            session: null,
            campaigns: [],
            callbacks: [],
            statsToday: {},
            coaching: {},
            vicidialAgentUrl: "",
            vicidialLive: {},
            vicidialConsoleUrl: "",
            vicidialWebphoneUrl: "",
            webphoneRegistered: false,
            phone: {},
            selectedCampaignId: null,
            manualDialPhone: "",
            manualDialBusy: false,
            cidAliases: [],
            outboundGroupAlias: "",
            // --- Hub d'appels (liste, fiche CRM, messagerie) ---
            recentCalls: [],
            callFilter: "all",
            callSearch: "",
            selectedCallId: null,
            centerContact: null,
            contact: null,
            contactLoading: false,
            noteText: "",
            noteSaving: false,
            messaging: { installed: false, sms: false, whatsapp: false },
            showDialpad: true,
            showScript: false,
            scriptHtml: null,
            showWebphone: false,
            showSessionMenu: false,
            callElapsed: 0,
            compose: { open: false, channel: "sms", body: "" },
            composeBusy: false,
            activityBusy: false,
            qualificationOptions: [],
            qualificationBusy: false,
            mobilePane: "dialer",
        });
        this._timer = null;
        this._heartbeatTimer = null;
        this._callTimer = null;
        this._callStart = null;
        this._searchTimer = null;
        this._lastPauseAlertKey = null;
        this._crmDialPending = false;
        this._onMobileResize = () => this._applyMobileLayout();

        onMounted(() => {
            this._applyMobileLayout();
            window.addEventListener("resize", this._onMobileResize);
            this.load();
            this._applyCrmDialIntent();
            this._scheduleRefresh();
            this._scheduleHeartbeat();
            this._scheduleCallTimer();
        });
        onWillUnmount(() => {
            window.removeEventListener("resize", this._onMobileResize);
            this._clearRefreshTimer();
            this._clearHeartbeatTimer();
            this._clearCallTimer();
            if (this._searchTimer) {
                clearTimeout(this._searchTimer);
            }
        });
    }


    _applyCrmDialIntent() {
        const params = (this.props.action && this.props.action.params) || {};
        let phone = (params.doorway_vicidial_dial_phone || "").trim();
        if (!phone && typeof window !== "undefined") {
            phone = (new URLSearchParams(window.location.search).get("phone") || "").trim();
        }
        const leadId = params.doorway_vicidial_lead_id;
        if (!phone) {
            return;
        }
        this.state.manualDialPhone = phone;
        this._crmDialPending = true;
        this.loadContact({ phone, lead_id: leadId });
        this.notification.add(
            "Numéro chargé depuis la fiche CRM — démarrez la session puis composez (ou attente auto si déjà en ligne).",
            { type: "info", title: "Appels" }
        );
    }

    _maybeAutoDialFromCrm() {
        if (!this._crmDialPending || !this.canManualDial()) {
            return;
        }
        this._crmDialPending = false;
        this.manualDial();
    }

    _applyMobileLayout() {
        const root = this.el;
        if (!root) {
            return;
        }
        const mobile = window.matchMedia(MOBILE_MQ).matches;
        const compact = window.matchMedia(COMPACT_MQ).matches;
        const wasMobile = root.classList.contains("o_vphub--mobile");
        root.classList.toggle("o_vphub--mobile", mobile);
        root.classList.toggle("o_vphub--compact", mobile && compact);
        if (mobile) {
            this.state.showDialpad = true;
            if (!wasMobile) {
                this.state.mobilePane = "dialer";
            }
        }
    }

    _clearRefreshTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    _clearHeartbeatTimer() {
        if (this._heartbeatTimer) {
            clearInterval(this._heartbeatTimer);
            this._heartbeatTimer = null;
        }
    }

    _clearCallTimer() {
        if (this._callTimer) {
            clearInterval(this._callTimer);
            this._callTimer = null;
        }
    }

    _scheduleCallTimer() {
        this._clearCallTimer();
        this._callTimer = setInterval(() => this._tickCall(), CALL_TICK_MS);
    }

    _tickCall() {
        const active = this.isCallActive();
        if (!active) {
            this._callStart = null;
            if (this.state.callElapsed !== 0) {
                this.state.callElapsed = 0;
            }
            return;
        }
        if (!this._callStart) {
            this._callStart = Date.now();
        }
        this.state.callElapsed = Math.floor((Date.now() - this._callStart) / 1000);
    }

    isCallActive() {
        const status = ((this.state.vicidialLive || {}).status || "").toUpperCase();
        return status === "INCALL" || status === "QUEUE";
    }

    formatTimer() {
        const total = Number(this.state.callElapsed) || 0;
        const m = Math.floor(total / 60);
        const s = total % 60;
        return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    _scheduleHeartbeat() {
        this._clearHeartbeatTimer();
        if (!this.state.session || this.state.session.state !== "active") {
            return;
        }
        this._heartbeatTimer = setInterval(() => this._sendHeartbeat(), HEARTBEAT_MS);
    }

    async _sendHeartbeat() {
        if (!this.state.session || this.state.session.state !== "active") {
            return;
        }
        try {
            const response = await fetch("/doorway/vicidial/workstation/heartbeat", {
                method: "POST",
                credentials: "same-origin",
            });
            if (!response.ok) {
                return;
            }
            const data = await response.json();
            if (data.vicidial_live) {
                this.state.vicidialLive = data.vicidial_live;
                if (this.state.session) {
                    this.state.session.vicidial_status =
                        data.vicidial_live.status || "";
                    this.state.session.vicidial_ready = !!data.vicidial_live.ready;
                }
            }
            if (typeof data.webphone_registered === "boolean") {
                this._applyWebphoneRegistered(data);
            }
            this._maybeAutoDialFromCrm();
        } catch (_e) {
            // Le poll workstation / cron keepalive prennent le relais.
        }
    }

    _scheduleRefresh() {
        this._clearRefreshTimer();
        const interval =
            this.state.session && this.state.session.state === "active"
                ? REFRESH_MS_ACTIVE
                : REFRESH_MS;
        this._timer = setInterval(() => this.load(false), interval);
    }

    _handlePauseAlerts(data) {
        const alert = data.pause_alert || {};
        if (!alert.active) {
            return;
        }
        const key = [
            alert.reason || "",
            alert.pause_code || "",
            alert.paused_seconds || 0,
        ].join("|");
        if (key === this._lastPauseAlertKey) {
            return;
        }
        this._lastPauseAlertKey = key;
        const mins = Math.max(Math.floor((alert.paused_seconds || 0) / 60), 0);
        const duration = mins > 0 ? `${mins} min` : "quelques secondes";
        this.notification.add(
            `⚠️ Pause automatique (${alert.reason || "SYSTEM"}) depuis ${duration}. ` +
                (alert.message || "Vérifiez le dialpad et cliquez Reprendre si besoin."),
            { type: "warning", sticky: true }
        );
        if (data.auto_pause_recovered) {
            this.notification.add(
                "Reprise automatique : vous êtes de nouveau READY.",
                { type: "success" }
            );
        }
    }

    formatDuration(seconds) {
        const s = Number(seconds) || 0;
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        return `${h}h${String(m).padStart(2, "0")}`;
    }

    async _fetchWorkstationData(light = false, maxAttempts = 3) {
        const url = light
            ? "/doorway/vicidial/workstation?light=1"
            : "/doorway/vicidial/workstation";
        let lastError = null;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000);
            try {
                const response = await fetch(url, {
                    credentials: "same-origin",
                    signal: controller.signal,
                });
                clearTimeout(timeoutId);
                if (response.status === 403) {
                    const err = new Error("no_access");
                    err.code = "no_access";
                    throw err;
                }
                if (!response.ok) {
                    throw new Error(`workstation_http_${response.status}`);
                }
                const contentType = response.headers.get("content-type") || "";
                if (!contentType.includes("application/json")) {
                    throw new Error("workstation_not_json");
                }
                return await response.json();
            } catch (error) {
                clearTimeout(timeoutId);
                lastError = error;
                if (attempt < maxAttempts) {
                    await new Promise((resolve) =>
                        setTimeout(resolve, 800 * attempt)
                    );
                }
            }
        }
        throw lastError || new Error("workstation_load_failed");
    }

    _applyWebphoneRegistered(data) {
        const liveSt = (
            ((data && data.vicidial_live) || this.state.vicidialLive || {})
                .status || ""
        ).toUpperCase();
        if (liveSt === "INCALL" || liveSt === "QUEUE" || liveSt === "DIAL") {
            this.state.webphoneRegistered = true;
            return;
        }
        this.state.webphoneRegistered = !!(data && data.webphone_registered);
    }

    async load(showSpinner = true) {
        if (showSpinner) {
            this.state.loading = true;
        }
        try {
            const data = await this._fetchWorkstationData(!showSpinner);
            this.state.agent = data.agent || {};
            this.state.session = data.session || null;
            this.state.campaigns = data.campaigns || [];
            this.state.callbacks = data.callbacks || [];
            this.state.statsToday = data.stats_today || {};
            this.state.vicidialAgentUrl = data.vicidial_agent_url || "";
            this.state.phone = data.phone || {};
            this.state.vicidialLive = data.vicidial_live || {};
            this._applyWebphoneRegistered(data);
            this.state.recentCalls = data.recent_calls || [];
            this.state.messaging =
                data.messaging || { installed: false, sms: false, whatsapp: false };
            this.state.qualificationOptions = data.qualification_options || [];
            this.state.cidAliases = data.cid_aliases || [];
            if (this.state.session) {
                this.state.outboundGroupAlias =
                    this.state.session.outbound_group_alias_id || "";
            }
            this._handlePauseAlerts(data);
            if (this.state.session && this.state.session.vicidial_webphone_url) {
                this.state.vicidialWebphoneUrl =
                    this.state.session.vicidial_webphone_url;
            }
            if (this.state.campaigns.length === 1) {
                this.state.selectedCampaignId = this.state.campaigns[0].id;
            } else if (!this.state.selectedCampaignId && this.state.campaigns.length) {
                const france = this.state.campaigns.find(
                    (c) => c.vicidial_campaign_id === "DW_FRB2C"
                );
                const withHopper = this.state.campaigns
                    .filter((c) => (c.hopper_count || 0) > 0)
                    .sort((a, b) => (b.hopper_count || 0) - (a.hopper_count || 0));
                this.state.selectedCampaignId =
                    (france && france.id) ||
                    (withHopper[0] && withHopper[0].id) ||
                    this.state.campaigns[0].id;
            }
            if (this.leadSync.setSessionActive) {
                this.leadSync.setSessionActive(!!this.state.session);
            }
            try {
                this._syncFocusFromState();
            } catch (_syncErr) {
                // Ne pas invalider tout le chargement si la synchro focus échoue.
            }
            this._maybeAutoDialFromCrm();
            this._scheduleRefresh();
            this._scheduleHeartbeat();
        } catch (error) {
            if (showSpinner) {
                const msg =
                    error && error.code === "no_access"
                        ? "Accès refusé au poste d'appels."
                        : "Impossible de charger le poste d'appels. Réessayez dans quelques secondes.";
                this.notification.add(msg, { type: "danger" });
            }
        } finally {
            this.state.loading = false;
        }
    }

    _syncFocusFromState() {
        // Met le focus sur l'appel en cours dès qu'il apparaît dans la liste.
        const activeCall = this.state.recentCalls.find((c) => c.active);
        if (activeCall && this.state.selectedCallId !== activeCall.id) {
            this.selectCall(activeCall);
            return;
        }
        // Sinon, à la première charge, on pré-sélectionne le contact le plus récent.
        if (
            !this.state.selectedCallId &&
            !this.state.centerContact &&
            this.state.recentCalls.length
        ) {
            this.selectCall(this.state.recentCalls[0]);
        }
    }

    onCampaignChange(ev) {
        this.state.selectedCampaignId = Number(ev.target.value) || null;
    }

    onOutboundAliasChange(ev) {
        this.state.outboundGroupAlias = ev.target.value || "";
        this._persistOutboundAlias();
    }

    async _persistOutboundAlias() {
        if (!this.state.session) {
            return;
        }
        try {
            const data = await this._postJson(
                "/doorway/vicidial/workstation/set_outbound_alias",
                { group_alias_id: this.state.outboundGroupAlias || "" }
            );
            if (this.state.session) {
                this.state.session.outbound_group_alias_id =
                    data.outbound_group_alias_id || "";
            }
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        }
    }

    async _post(url) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
        });
        return this._parseJsonResponse(response);
    }

    async _parseJsonResponse(response) {
        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            if (response.status === 502 || response.status === 503) {
                throw new Error(
                    "Serveur Odoo en redémarrage — réessayez dans quelques secondes."
                );
            }
            if (response.status === 401 || response.status === 403) {
                throw new Error("session_expired");
            }
            throw new Error("unexpected_token");
        }
        let data = {};
        try {
            data = await response.json();
        } catch (_e) {
            throw new Error("unexpected_token");
        }
        if (!response.ok) {
            throw new Error(data.error || "request_failed");
        }
        return data;
    }

    async _postJson(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        return this._parseJsonResponse(response);
    }

    onManualDialPhoneInput(ev) {
        this.state.manualDialPhone = ev.target.value;
    }

    onManualDialKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.manualDial();
        }
    }

    _manualDialReady() {
        return (
            this.state.session &&
            this.state.session.state === "active" &&
            this.state.session.vicidial_ready &&
            this.state.webphoneRegistered
        );
    }

    canManualDial() {
        return (
            this._manualDialReady() &&
            !!(this.state.manualDialPhone || "").trim() &&
            !this.state.manualDialBusy
        );
    }

    async manualDial() {
        const phone = (this.state.manualDialPhone || "").trim();
        if (!phone) {
            return;
        }
        if (!this._manualDialReady()) {
            if (!this.state.session) {
                this.state.showSessionMenu = true;
                this.notification.add(
                    "Démarrez une session : cliquez sur « Hors ligne » puis « Démarrer ».",
                    { type: "warning", sticky: true }
                );
            } else if (!this.state.webphoneRegistered) {
                this.notification.add(
                    "Attendez que le téléphone affiche « En ligne » avec la pastille verte.",
                    { type: "warning", sticky: true }
                );
            } else {
                this.notification.add(
                    "Attendez que la pastille affiche « Prêt » avant d'appeler.",
                    { type: "warning" }
                );
            }
            return;
        }
        if (this.state.manualDialBusy) {
            return;
        }
        this.state.manualDialBusy = true;
        try {
            const data = await this._postJson(
                "/doorway/vicidial/workstation/manual_dial",
                {
                    phone,
                    group_alias_id: this.state.outboundGroupAlias || "",
                }
            );
            if (data.vicidial_live) {
                this.state.vicidialLive = data.vicidial_live;
                this.state.session.vicidial_status = data.vicidial_live.status || "";
                this.state.session.vicidial_ready = !!data.vicidial_live.ready;
            }
            const liveStatus = (
                (data.vicidial_live && data.vicidial_live.status) || ""
            ).toUpperCase();
            let dialed = data.phone_number || phone;
            if ((String(dialed).replace(/\D/g, "") || "").length < 8) {
                dialed = phone;
            }
            this.state.centerContact = {
                name: dialed,
                phone: dialed,
                initials: dialed.replace(/\D/g, "").slice(-2) || "?",
                color: "#6366f1",
                location: "",
            };
            if (liveStatus === "INCALL" || liveStatus === "QUEUE") {
                this.notification.add(`Appel en cours vers ${dialed}…`, {
                    type: "success",
                });
            } else {
                this.notification.add(
                    `Composition lancée vers ${dialed} — en attente du bridge VICIdial…`,
                    { type: "warning" }
                );
            }
            // Rafraîchit la fiche CRM pour le numéro composé.
            this.loadContact({ phone: dialed });
            this.reloadRecentCalls();
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        } finally {
            this.state.manualDialBusy = false;
        }
    }

    openWebphoneTab() {
        window.open("/doorway/vicidial/webphone", "_blank", "noopener");
    }

    selectedCampaign() {
        return (
            this.state.campaigns.find(
                (c) => c.id === this.state.selectedCampaignId
            ) || null
        );
    }

    campaignAllowsManual(camp) {
        return !!(camp && camp.manual_dial);
    }

    manualDialPlaceholder() {
        const hint =
            (this.state.session && this.state.session.manual_dial_hint) || "";
        if (hint) {
            return hint;
        }
        const camp = this.selectedCampaign();
        const cid = ((camp && camp.vicidial_campaign_id) || "").toUpperCase();
        if (cid.startsWith("DW_QC") || cid === "DW_RAPQC") {
            return "Ex. 5145551234 (sans +1)";
        }
        if (cid.startsWith("DW_ES") || cid.includes("ABD")) {
            return "Ex. 612345678 (sans +34)";
        }
        return "Ex. 0478820581 ou 0612345678 (sans +33)";
    }

    canStartCampaign(camp) {
        if (!camp) {
            return false;
        }
        if ((camp.hopper_count || 0) > 0) {
            return true;
        }
        return this.campaignAllowsManual(camp);
    }

    singleCampaignMode() {
        return this.state.campaigns.length === 1;
    }

    sessionPillClass() {
        if (!this.state.session) {
            return "o_vphub_status--off";
        }
        if (this.state.session.state === "paused") {
            return "o_vphub_status--pause";
        }
        if (this.state.session.vicidial_ready && this.state.webphoneRegistered) {
            return "o_vphub_status--on";
        }
        return "o_vphub_status--connecting";
    }

    sessionPillLabel() {
        if (!this.state.session) {
            return "Hors ligne";
        }
        if (this.state.session.state === "paused") {
            return "En pause";
        }
        if (this.state.session.vicidial_ready && this.state.webphoneRegistered) {
            return "Prêt";
        }
        if (this.state.session.vicidial_ready) {
            return "En ligne";
        }
        return "Connexion…";
    }

    toggleSessionMenu() {
        this.state.showSessionMenu = !this.state.showSessionMenu;
    }

    closeSessionMenu() {
        this.state.showSessionMenu = false;
    }

    onSessionPillClick() {
        if (!this.state.session && this.singleCampaignMode() && this.state.selectedCampaignId) {
            const camp = this.selectedCampaign();
            if (camp && this.canStartCampaign(camp)) {
                this.startSession();
                return;
            }
        }
        this.toggleSessionMenu();
    }

    async startSession() {
        if (!this.state.selectedCampaignId) {
            return;
        }
        const camp = this.selectedCampaign();
        if (camp && !this.canStartCampaign(camp)) {
            this.notification.add(
                `Aucun prospect à appeler pour « ${camp.name} » (hopper vide). Choisissez une autre campagne.`,
                { type: "danger" }
            );
            return;
        }
        try {
            const data = await this._post(
                `/doorway/vicidial/workstation/start?campaign_id=${this.state.selectedCampaignId}`
            );
            this.state.session = data.session;
            this.state.outboundGroupAlias =
                (data.session && data.session.outbound_group_alias_id) || "";
            this.state.vicidialWebphoneUrl =
                (data.session && data.session.vicidial_webphone_url) || "";
            if (this.leadSync.setSessionActive) {
                this.leadSync.setSessionActive(true);
            }
            if (this.state.vicidialWebphoneUrl) {
                this.notification.add(
                    "Session démarrée — ouvrez le téléphone (pastille ou plein écran) et autorisez le micro.",
                    { type: "info", sticky: true }
                );
            } else if (data.session && data.session.vicidial_ready) {
                this.notification.add(
                    "Session démarrée — vous êtes READY, les appels vont partir.",
                    { type: "success" }
                );
            } else {
                this.notification.add(
                    "Session démarrée — connexion VICIdial en cours.",
                    { type: "warning" }
                );
            }
            await this.load(false);
            this._scheduleHeartbeat();
            this.closeSessionMenu();
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        }
    }

    async pauseTyped(pauseType) {
        try {
            const data = await this._post(`/pe/workstation/pause/${pauseType}`);
            this.state.session = data.session;
            if (this.leadSync.setSessionActive) {
                this.leadSync.setSessionActive(false);
            }
            this._clearHeartbeatTimer();
            this.closeSessionMenu();
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        }
    }

    async pausePausette() {
        return this.pauseTyped("pausette");
    }

    async pauseDejeuner() {
        return this.pauseTyped("dejeuner");
    }

    async pauseSession() {
        try {
            const data = await this._post("/doorway/vicidial/workstation/pause");
            this.state.session = data.session;
            if (this.leadSync.setSessionActive) {
                this.leadSync.setSessionActive(false);
            }
            this._clearHeartbeatTimer();
            this.closeSessionMenu();
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        }
    }

    async resumeSession() {
        try {
            const data = await this._post("/doorway/vicidial/workstation/resume");
            this.state.session = data.session;
            if (this.leadSync.setSessionActive) {
                this.leadSync.setSessionActive(true);
            }
            this._scheduleHeartbeat();
            this.closeSessionMenu();
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        }
    }

    onPauseControl() {
        if (!this.state.session) {
            return;
        }
        if (this.state.session.state === "active") {
            this.pauseSession();
        } else if (this.state.session.state === "paused") {
            this.resumeSession();
        }
    }

    async dialNextLead() {
        if (!this.state.session || this.state.session.state !== "active") {
            return;
        }
        if (!this.state.session.vicidial_ready) {
            this.notification.add(
                "Attendez que la pastille affiche « Prêt » avant d'appeler.",
                { type: "warning" }
            );
            return;
        }
        if (!this.state.webphoneRegistered) {
            this.notification.add(
                "Attendez que le téléphone affiche « En ligne » avec la pastille verte.",
                { type: "warning", sticky: true }
            );
            return;
        }
        try {
            const data = await this._postJson(
                "/doorway/vicidial/workstation/dial-next",
                { group_alias_id: this.state.outboundGroupAlias || "" }
            );
            if (data.vicidial_live) {
                this.state.vicidialLive = data.vicidial_live;
                this.state.session.vicidial_status = data.vicidial_live.status || "";
                this.state.session.vicidial_ready = !!data.vicidial_live.ready;
            }
            const phone = data.phone_number || "";
            const liveStatus = (
                (data.vicidial_live && data.vicidial_live.status) || ""
            ).toUpperCase();
            if (liveStatus === "INCALL" || liveStatus === "QUEUE") {
                this.notification.add(
                    phone
                        ? `Appel en cours vers ${phone}…`
                        : "Appel lancé — le téléphone va sonner.",
                    { type: "success" }
                );
            } else {
                this.notification.add(
                    phone
                        ? `Composition vers ${phone} — en attente du bridge VICIdial…`
                        : "Appel demandé — en attente du bridge VICIdial…",
                    { type: "warning" }
                );
            }
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        }
    }

    async endSession() {
        try {
            const data = await this._post("/doorway/vicidial/workstation/end");
            this.state.session = null;
            if (this.leadSync.setSessionActive) {
                this.leadSync.setSessionActive(false);
            }
            this.notification.add("Session terminée — stats enregistrées dans RH.", {
                type: "info",
            });
            this._clearHeartbeatTimer();
            this.closeSessionMenu();
            await this.load(false);
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        }
    }

    async pauseSessionAndClose() {
        await this.pauseSession();
        this.closeSessionMenu();
    }

    async resumeSessionAndClose() {
        await this.resumeSession();
    }

    async endSessionAndClose() {
        await this.endSession();
    }

    async startSessionAndClose() {
        await this.startSession();
    }

    openQualification() {
        this.action.doAction("doorway_vicidial_campaigns.action_vicidial_qualification");
    }

    openCalendar() {
        this.action.doAction("doorway_vicidial_campaigns.action_vicidial_callbacks_calendar");
    }

    openMyCoaching() {
        this.action.doAction("doorway_vicidial_campaigns.action_my_coaching_dashboard");
    }

    openLead(leadId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "crm.lead",
            res_id: leadId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ------------------------------------------------------------------
    // Hub d'appels — liste à gauche
    // ------------------------------------------------------------------

    setCallFilter(kind) {
        this.state.callFilter = kind;
        this.reloadRecentCalls();
    }

    onCallSearchInput(ev) {
        this.state.callSearch = ev.target.value;
        if (this._searchTimer) {
            clearTimeout(this._searchTimer);
        }
        this._searchTimer = setTimeout(
            () => this.reloadRecentCalls(),
            SEARCH_DEBOUNCE_MS
        );
    }

    async reloadRecentCalls() {
        try {
            const params = new URLSearchParams();
            params.set("kind", this.state.callFilter || "all");
            if ((this.state.callSearch || "").trim()) {
                params.set("search", this.state.callSearch.trim());
            }
            const resp = await fetch(
                "/doorway/vicidial/workstation/recent_calls?" + params.toString(),
                { credentials: "same-origin" }
            );
            if (!resp.ok) {
                return;
            }
            const data = await resp.json();
            this.state.recentCalls = data.calls || [];
        } catch (_e) {
            // Liste précédente conservée.
        }
    }

    callBadgeLabel(call) {
        if (call.status === "manque") {
            return "Manqué";
        }
        return call.direction === "entrant" ? "Entrant" : "Sortant";
    }

    callBadgeClass(call) {
        if (call.status === "manque") {
            return "o_vphub_badge--missed";
        }
        return call.direction === "entrant"
            ? "o_vphub_badge--in"
            : "o_vphub_badge--out";
    }

    selectCall(call) {
        this.state.selectedCallId = call.id;
        this.state.centerContact = {
            name: call.name,
            phone: call.phone,
            initials: call.initials,
            color: call.color,
            location: "",
        };
        this.loadContact({ phone: call.phone, lead_id: call.lead_id });
    }

    // ------------------------------------------------------------------
    // Fiche contact CRM — panneau de droite
    // ------------------------------------------------------------------

    async loadContact({ phone, lead_id, partner_id } = {}) {
        this.state.contactLoading = true;
        try {
            const params = new URLSearchParams();
            if (phone) {
                params.set("phone", phone);
            }
            if (lead_id) {
                params.set("lead_id", lead_id);
            }
            if (partner_id) {
                params.set("partner_id", partner_id);
            }
            const resp = await fetch(
                "/doorway/vicidial/workstation/contact?" + params.toString(),
                { credentials: "same-origin" }
            );
            if (!resp.ok) {
                throw new Error("contact_load_failed");
            }
            const data = await resp.json();
            this.state.contact = data.contact || null;
            this.state.noteText = "";
            this.state.compose.open = false;
            if (this.state.contact) {
                this.state.centerContact = {
                    name: this.state.contact.name,
                    phone: this.state.contact.phone || phone || "",
                    initials: this.state.contact.initials,
                    color: this.state.contact.color,
                    location: this.state.contact.company || "",
                };
            }
            if (this.state.contact && this.state.centerContact) {
                this.state.centerContact.location = this.state.contact.company || "";
            }
        } catch (_e) {
            this.state.contact = null;
        } finally {
            this.state.contactLoading = false;
        }
    }

    _contactPhone() {
        const c = this.state.contact;
        if (c && (c.mobile || c.phone)) {
            return (c.mobile || c.phone).trim();
        }
        if (this.state.centerContact && this.state.centerContact.phone) {
            return this.state.centerContact.phone.trim();
        }
        return (this.state.manualDialPhone || "").trim();
    }

    dialPhoneAvailable() {
        return !!this._contactPhone();
    }

    setMobilePane(pane) {
        this.state.mobilePane = pane;
        this.state.showSessionMenu = false;
        const tabs = document.querySelector(".o_vphub_mobile_tabs");
        if (tabs && window.matchMedia("(max-width: 1200px)").matches) {
            tabs.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
    }

    onMobileTabClick(pane, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        this.setMobilePane(pane);
    }

    onManualDialPhoneFocus(ev) {
        if (!window.matchMedia("(max-width: 1200px)").matches) {
            return;
        }
        const el = ev.target;
        window.setTimeout(() => {
            el.scrollIntoView({ block: "center", behavior: "smooth" });
        }, 320);
    }

    openContactInCrm() {
        const c = this.state.contact;
        if (c && c.lead_id) {
            this.openLead(c.lead_id);
            return;
        }
        if (c && c.partner_id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: c.partner_id,
                view_mode: "form",
                views: [[false, "form"]],
                target: "current",
            });
            return;
        }
        this.notification.add("Aucune fiche CRM liée à ce contact.", {
            type: "warning",
        });
    }

    onNoteInput(ev) {
        this.state.noteText = ev.target.value;
    }

    async saveNote() {
        const note = (this.state.noteText || "").trim();
        if (!note) {
            return;
        }
        const c = this.state.contact;
        if (!c || (!c.lead_id && !c.partner_id)) {
            this.notification.add(
                "Aucune fiche CRM pour enregistrer la note (lead ou contact requis).",
                { type: "warning" }
            );
            return;
        }
        this.state.noteSaving = true;
        try {
            await this._postJson("/doorway/vicidial/workstation/note", {
                note,
                lead_id: c.lead_id || null,
                partner_id: c.partner_id || null,
            });
            this.state.noteText = "";
            this.notification.add("Note d'appel enregistrée.", { type: "success" });
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        } finally {
            this.state.noteSaving = false;
        }
    }

    async _createActivity(kind, label) {
        const c = this.state.contact;
        if (!c || (!c.lead_id && !c.partner_id)) {
            this.notification.add(
                "Aucune fiche CRM pour créer une activité (lead ou contact requis).",
                { type: "warning" }
            );
            return;
        }
        if (this.state.activityBusy) {
            return;
        }
        this.state.activityBusy = true;
        try {
            await this._postJson("/doorway/vicidial/workstation/activity", {
                kind,
                lead_id: c.lead_id || null,
                partner_id: c.partner_id || null,
            });
            this.notification.add(`${label} créé(e).`, { type: "success" });
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        } finally {
            this.state.activityBusy = false;
        }
    }

    createTask() {
        this._createActivity("task", "Tâche");
    }

    scheduleFollowup() {
        this._createActivity("followup", "Suivi");
    }

    qualificationChipClass(opt) {
        const tone = opt.tone || "muted";
        let cls = `o_vphub_qualif__chip o_vphub_qualif__chip--${tone}`;
        const c = this.state.contact;
        if (c && c.qualification_statut === opt.code) {
            cls += " o_vphub_qualif__chip--active";
        }
        return cls;
    }

    async applyQualification(code) {
        const c = this.state.contact;
        if (!c || !c.lead_id) {
            this.notification.add(
                "Qualification CRM : une fiche lead est requise pour ce contact.",
                { type: "warning" }
            );
            return;
        }
        if (this.state.qualificationBusy) {
            return;
        }
        this.state.qualificationBusy = true;
        try {
            const note = (this.state.noteText || "").trim();
            const data = await this._postJson("/doorway/vicidial/workstation/qualify", {
                statut: code,
                lead_id: c.lead_id,
                partner_id: c.partner_id || null,
                note: note || null,
            });
            if (data.qualification_statut) {
                c.qualification_statut = data.qualification_statut;
            }
            if (data.qualification_label) {
                c.qualification_label = data.qualification_label;
            }
            if (data.note_saved) {
                this.state.noteText = "";
            }
            this.notification.add(
                `Qualification enregistrée : ${data.qualification_label || code}`,
                { type: "success" }
            );
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        } finally {
            this.state.qualificationBusy = false;
        }
    }

    // ------------------------------------------------------------------
    // SMS / WhatsApp (doorway_messaging) avec dégradation gracieuse
    // ------------------------------------------------------------------

    smsEnabled() {
        return !!(this.state.messaging.installed && this.state.messaging.sms);
    }

    whatsappEnabled() {
        return !!(this.state.messaging.installed && this.state.messaging.whatsapp);
    }

    messagingTooltip(channel) {
        if (!this.state.messaging.installed) {
            return "Module Messagerie (doorway_messaging) non installé.";
        }
        const ok = channel === "sms" ? this.state.messaging.sms : this.state.messaging.whatsapp;
        if (!ok) {
            return "Twilio non configuré pour ce canal.";
        }
        return channel === "sms" ? "Envoyer un SMS" : "Envoyer un WhatsApp";
    }

    openCompose(channel) {
        if (!this._contactPhone()) {
            this.notification.add("Aucun numéro de téléphone pour ce contact.", {
                type: "warning",
            });
            return;
        }
        this.state.compose = { open: true, channel, body: "" };
    }

    closeCompose() {
        this.state.compose.open = false;
    }

    onComposeInput(ev) {
        this.state.compose.body = ev.target.value;
    }

    async sendMessage() {
        const channel = this.state.compose.channel;
        const body = (this.state.compose.body || "").trim();
        const phone = this._contactPhone();
        if (!phone) {
            this.notification.add("Aucun numéro de téléphone pour ce contact.", {
                type: "warning",
            });
            return;
        }
        if (!body) {
            this.notification.add("Le message est vide.", { type: "warning" });
            return;
        }
        const c = this.state.contact || {};
        this.state.composeBusy = true;
        try {
            await this._postJson("/doorway/vicidial/workstation/send_message", {
                channel,
                phone,
                body,
                lead_id: c.lead_id || null,
                partner_id: c.partner_id || null,
            });
            this.notification.add(
                channel === "sms" ? "SMS envoyé." : "WhatsApp envoyé.",
                { type: "success" }
            );
            this.state.compose.open = false;
            this.state.compose.body = "";
        } catch (e) {
            this.notification.add(this._messageError(String(e.message || e)), {
                type: "danger",
            });
        } finally {
            this.state.composeBusy = false;
        }
    }

    _messageError(code) {
        const map = {
            module_absent: "Module Messagerie non installé.",
            sms_unavailable: "Twilio SMS non configuré.",
            wa_unavailable: "Twilio WhatsApp non configuré.",
            no_phone: "Numéro de téléphone manquant.",
            bad_channel: "Canal inconnu.",
            send_failed: "Échec de l'envoi.",
        };
        return map[code] || code;
    }

    // ------------------------------------------------------------------
    // Pavé numérique + contrôles d'appel
    // ------------------------------------------------------------------

    pressDigit(digit) {
        this.state.manualDialPhone = (this.state.manualDialPhone || "") + digit;
    }

    dialBackspace() {
        this.state.manualDialPhone = (this.state.manualDialPhone || "").slice(0, -1);
    }

    dialClear() {
        this.state.manualDialPhone = "";
    }

    toggleDialpad() {
        this.state.showDialpad = !this.state.showDialpad;
    }

    prefillSMSDriven() {
        const lead = this.state.currentLead;
        const prenom = lead && lead.prenom ? lead.prenom : (lead && lead.partner_name ? lead.partner_name.split(' ')[0] : '');
        const msg = prenom
            ? `Bonjour ${prenom}, suite a notre appel — voici votre lien pour soumettre votre dossier de financement en 3 min: https://fr.driven.ca/partners/agence-doorway — Code partenaire: DOORWAY. Des questions? Repondez a ce message.`
            : `Bonjour, suite a notre appel — voici votre lien pour soumettre votre dossier de financement en 3 min: https://fr.driven.ca/partners/agence-doorway — Code partenaire: DOORWAY. Des questions? Repondez a ce message.`;
        this.state.compose.body = msg;
        this.state.compose.open = true;
        this.state.compose.channel = 'sms';
    }

    async toggleScript() {
        if (this.state.showScript) {
            this.state.showScript = false;
            return;
        }
        // Charger le script de la campagne active
        try {
            const campaignId = this.state.session && this.state.session.campaign_id;
            if (campaignId) {
                const result = await this.orm.call(
                    'doorway.vicidial.campaign',
                    'get_script_html',
                    [campaignId]
                );
                this.state.scriptHtml = result || '<p>Aucun script pour cette campagne.</p>';
            } else {
                this.state.scriptHtml = '<p>Aucune campagne active.</p>';
            }
        } catch(e) {
            this.state.scriptHtml = '<p>Erreur chargement script.</p>';
        }
        this.state.showScript = true;
    }

    toggleWebphone() {
        this.state.showWebphone = !this.state.showWebphone;
    }

    _revealWebphone(message) {
        this.state.showWebphone = true;
        if (message) {
            this.notification.add(message, { type: "info" });
        }
    }

    onMuteCall() {
        this._revealWebphone("Coupez/réactivez le micro depuis le téléphone intégré.");
    }

    onTransferCall() {
        this._revealWebphone("Transférez l'appel depuis le téléphone intégré.");
    }

    onRecordCall() {
        this._revealWebphone("L'enregistrement se gère depuis le téléphone intégré.");
    }

    onAnswerCall() {
        // Si un numéro est composé, on lance l'appel manuel réel (VICIdial).
        if ((this.state.manualDialPhone || "").trim()) {
            this.manualDial();
            return;
        }
        this._revealWebphone("Répondez à l'appel depuis le téléphone intégré.");
    }

    async onHangupCall() {
        const sessionActive =
            this.state.session && this.state.session.state === "active";
        const vicidialLoggedIn = !!(this.state.vicidialLive || {}).logged_in;
        if (!sessionActive && !vicidialLoggedIn) {
            this.notification.add("Session inactive.", { type: "warning" });
            return;
        }
        try {
            const data = await this._postJson(
                "/doorway/vicidial/workstation/hangup",
                {}
            );
            if (data.vicidial_live) {
                this.state.vicidialLive = data.vicidial_live;
                if (this.state.session) {
                    this.state.session.vicidial_status =
                        data.vicidial_live.status || "";
                    this.state.session.vicidial_ready = !!data.vicidial_live.ready;
                }
            }
            if (data.skipped) {
                this.notification.add(
                    data.message || "Aucun appel actif à raccrocher.",
                    { type: "info" }
                );
                return;
            }
            this.state.manualDialPhone = "";
            this.state.callElapsed = 0;
            this._callStart = null;
            this.notification.add(
                data.message || "Appel raccroché.",
                { type: "success" }
            );
            this.reloadRecentCalls();
        } catch (e) {
            const msg = String(e.message || e);
            if (msg === "session_expired") {
                this.notification.add(
                    "Session expirée — rechargez la page (Ctrl+F5).",
                    { type: "warning" }
                );
                return;
            }
            this.notification.add(msg, { type: "danger" });
        }
    }
}

registry.category("actions").add(
    "vicidial_workstation_action",
    VicidialWorkstation
);
