/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ELEVENLABS_CLIENT_CDN =
    "https://cdn.jsdelivr.net/npm/@elevenlabs/client@0.5.0/+esm";

function rpcErrorMessage(err) {
    return (
        err?.data?.message ||
        err?.data?.arguments?.[0] ||
        err?.message ||
        "Erreur inconnue."
    );
}

async function loadElevenLabsConversation() {
    const mod = await import(/* webpackIgnore: true */ ELEVENLABS_CLIENT_CDN);
    return mod.Conversation;
}

class AgentWebCall extends Component {
    static template = "doorway_agents_dashboard.AgentWebCall";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.conversation = null;
        this.micStream = null;
        this.startedAt = null;
        this.userRequestedEnd = false;
        this._lastSessionError = "";
        this._startAttempt = 0;
        this.state = useState({
            phase: "idle",
            agentName: "",
            stackLabel: "",
            scenarioHint: "",
            fallbackReason: "",
            scriptLabel: "",
            scriptPreview: "",
            scriptHasImprovements: false,
            scriptIsLinked: false,
            firstMessagePreview: "",
            error: "",
            statusText: "Prêt à démarrer",
            agentMode: "",
            transcriptLines: [],
            durationSec: 0,
            result: null,
            rating: 4,
            comment: "",
            issues: {
                tone: false,
                script: false,
                qualification: false,
                latency: false,
                actions: false,
                other: false,
            },
            aiResult: null,
            busy: false,
        });
        onMounted(() => this.bootstrap());
        onWillUnmount(() => this.cleanupSession());
    }

    get testCallId() {
        return this.props.action?.params?.test_call_id;
    }

    async bootstrap() {
        if (!this.testCallId) {
            this.state.phase = "error";
            this.state.error = "Identifiant d'appel test manquant.";
            return;
        }
        try {
            const prep = await this.orm.call(
                "doorway.agent.test.call",
                "web_test_preview",
                [this.testCallId]
            );
            if (prep.ok === false) {
                this.state.phase = "error";
                this.state.error =
                    prep.error ||
                    "Impossible de charger l'aperçu du test web pour cet agent.";
                return;
            }
            this.state.agentName = prep.agent_name || "";
            this.state.scenarioHint = prep.scenario_hint || "";
            this.state.fallbackReason = prep.fallback_reason || "";
            this.state.stackLabel =
                prep.stack === "n8n"
                    ? "n8n → Deepgram → Claude → ElevenLabs"
                    : prep.stack === "elevenlabs_fallback"
                      ? "ElevenLabs direct (secours — n8n indisponible)"
                      : prep.stack === "elevenlabs_direct"
                        ? "ElevenLabs direct (legacy / debug)"
                        : prep.stack || prep.provider || "";
            this.state.scriptLabel = prep.script_label || "";
            this.state.scriptPreview = prep.script_preview || "";
            this.state.scriptHasImprovements = !!prep.script_has_improvements;
            this.state.scriptIsLinked = !!prep.script_is_linked;
            this.state.firstMessagePreview = prep.first_message_preview || "";
            this._sessionConfig = null;
            this.state.phase = "ready";
            this.state.statusText =
                "Prêt — cliquez « Démarrer l'appel » (connexion ElevenLabs à ce moment)";
        } catch (err) {
            this.state.phase = "error";
            this.state.error = rpcErrorMessage(err);
        }
    }

    async startCall() {
        if (this.state.busy || this.state.phase === "live") {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        this.userRequestedEnd = false;
        this._lastSessionError = "";
        try {
            if (!this._startAttempt) {
                this._startAttempt = 1;
            }
            const prep = await this.orm.call(
                "doorway.agent.test.call",
                "web_test_prepare",
                [this.testCallId]
            );
            if (prep.ok === false) {
                throw new Error(prep.error || "Préparation test web échouée.");
            }
            this._sessionConfig = prep;
            this.state.scriptPreview = prep.script_preview || "";
            this.state.scriptHasImprovements = !!prep.script_has_improvements;
            this.state.scriptLabel = prep.script_label || "";
            this.state.firstMessagePreview = prep.first_message_preview || "";

            this.micStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });
            const Conversation = await loadElevenLabsConversation();
            const cfg = this._sessionConfig || {};
            const sessionArgs = {};
            if (cfg.conversation_token) {
                sessionArgs.conversationToken = cfg.conversation_token;
                sessionArgs.connectionType = "webrtc";
            } else if (cfg.signed_url) {
                sessionArgs.signedUrl = cfg.signed_url;
                sessionArgs.connectionType = "websocket";
            } else if (cfg.websocket_url) {
                throw new Error(
                    "Session WebSocket n8n détectée — connecteur navigateur en cours de déploiement. " +
                        "Demandez à l'équipe n8n un conversation_token ou signed_url."
                );
            } else {
                throw new Error(
                    "Session web indisponible. Vérifiez le workflow n8n start-web-test " +
                        "(conversation_token ou signed_url requis)."
                );
            }
            const dynamicVariables = cfg.dynamic_variables || {};
            if (Object.keys(dynamicVariables).length) {
                sessionArgs.dynamicVariables = dynamicVariables;
            }
            if (!cfg.conversation_token && !cfg.signed_url && cfg.elevenlabs_agent_id) {
                sessionArgs.agentId = cfg.elevenlabs_agent_id;
            }
            if (cfg.conversation_overrides && Object.keys(cfg.conversation_overrides).length) {
                sessionArgs.overrides = cfg.conversation_overrides;
            }

            this.conversation = await Conversation.startSession({
                ...sessionArgs,
                onConnect: () => {
                    this._startAttempt = 0;
                    this.state.phase = "live";
                    this.state.statusText =
                        "Connecté — l'agent va parler, vérifiez le volume du navigateur";
                    this.startedAt = Date.now();
                },
                onDisconnect: async () => {
                    if (this.userRequestedEnd || this.state.phase !== "live") {
                        return;
                    }
                    const elapsed = this.startedAt
                        ? Date.now() - this.startedAt
                        : 0;
                    if (elapsed < 12000 && this._startAttempt < 2) {
                        this._startAttempt += 1;
                        this.state.statusText = "Reconnexion…";
                        await this.cleanupSession();
                        this.state.busy = false;
                        await this.startCall();
                        return;
                    }
                    if (elapsed < 12000) {
                        this.state.phase = "ready";
                        this.state.agentMode = "";
                        this.state.statusText = "Connexion interrompue";
                        const detail = this._lastSessionError
                            ? ` Détail: ${this._lastSessionError}`
                            : "";
                        this.state.error =
                            "L'appel s'est coupé trop tôt. Vérifiez le volume du navigateur " +
                            "(icône haut-parleur dans la barre d'adresse), attendez que l'agent " +
                            "parle avant de répondre, puis réessayez." +
                            detail;
                        this.notification.add(this.state.error, { type: "warning" });
                        this._stopMicStream();
                        this._startAttempt = 0;
                        return;
                    }
                    this.endCall();
                },
                onModeChange: (mode) => {
                    this.state.agentMode = mode?.mode || mode || "";
                    if (this.state.agentMode === "speaking") {
                        this.state.statusText = "L'agent parle — écoutez vos haut-parleurs";
                    } else if (this.state.agentMode === "listening") {
                        this.state.statusText = "À vous — parlez dans le micro";
                    }
                },
                onMessage: (message) => {
                    const role = message.source === "user" ? "user" : "agent";
                    const text = message.message || message.text || "";
                    if (text) {
                        this.state.transcriptLines.push({ role, text });
                    }
                },
                onError: (err) => {
                    const msg = err?.message || String(err);
                    this._lastSessionError = msg;
                    this.state.error = msg;
                    this.notification.add(msg, { type: "danger" });
                },
                onDebug: (evt) => {
                    console.debug("[agent-web-call]", evt);
                },
            });
        } catch (err) {
            this.state.phase = "ready";
            this.state.error =
                err.message ||
                "Microphone ou connexion ElevenLabs refusé. Vérifiez les permissions.";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    _stopMicStream() {
        if (!this.micStream) {
            return;
        }
        for (const track of this.micStream.getTracks()) {
            track.stop();
        }
        this.micStream = null;
    }

    async endCall() {
        if (this.state.phase !== "live" && this.state.phase !== "ready") {
            return;
        }
        this.userRequestedEnd = true;
        this.state.busy = true;
        const duration = this.startedAt
            ? Math.round((Date.now() - this.startedAt) / 1000)
            : 0;
        this.state.durationSec = duration;
        let conversationId = "";
        try {
            if (this.conversation?.getId) {
                conversationId = this.conversation.getId() || "";
            }
            if (this.conversation?.endSession) {
                await this.conversation.endSession();
            }
        } catch (err) {
            console.warn("endSession", err);
        }
        this.conversation = null;
        this._stopMicStream();
        try {
            const result = await this.orm.call(
                "doorway.agent.test.call",
                "web_test_finalize",
                [
                    this.testCallId,
                    this.state.transcriptLines,
                    duration,
                    conversationId,
                ]
            );
            this.state.result = result;
            this.state.phase = "feedback";
            this.state.statusText = "Appel terminé — donnez votre avis";
        } catch (err) {
            this.state.phase = "error";
            this.state.error = rpcErrorMessage(err);
        } finally {
            this.state.busy = false;
        }
    }

    async cleanupSession() {
        try {
            if (this.conversation?.endSession) {
                await this.conversation.endSession();
            }
        } catch (_e) {
            /* ignore */
        }
        this.conversation = null;
        this._stopMicStream();
    }

    setRating(value) {
        this.state.rating = parseInt(value, 10) || 3;
    }

    toggleIssue(key) {
        this.state.issues[key] = !this.state.issues[key];
    }

    async submitFeedback() {
        if (!this.state.comment.trim()) {
            this.notification.add("Décrivez ce qui doit être amélioré.", {
                type: "warning",
            });
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call(
                "doorway.agent.feedback",
                "submit_from_web_test",
                [
                    this.testCallId,
                    this.state.rating,
                    this.state.comment,
                    this.state.issues,
                ]
            );
            this.state.phase = "assist";
            this.notification.add("Retour enregistré.", { type: "success" });
        } catch (err) {
            this.notification.add(err.message || "Erreur enregistrement.", {
                type: "danger",
            });
        } finally {
            this.state.busy = false;
        }
    }

    async runAiAssist() {
        this.state.busy = true;
        try {
            const result = await this.orm.call(
                "doorway.agent.test.call",
                "web_test_run_ai_assist",
                [this.testCallId]
            );
            this.state.aiResult = result;
            this.state.phase = "done";
            this.notification.add("Assistance IA terminée.", { type: "success" });
        } catch (err) {
            this.notification.add(err.message || "Assistance IA échouée.", {
                type: "danger",
            });
        } finally {
            this.state.busy = false;
        }
    }

    openPerformance() {
        const agentId = this._sessionConfig?.agent_id;
        if (!agentId) {
            this.action.doAction("doorway_agents_dashboard.action_agent_performance");
            return;
        }
        this.action.doAction({
            type: "ir.actions.client",
            tag: "performance_dashboard_action",
            name: "Performance IA",
            params: { agent_id: agentId },
        });
    }

    backToDashboard() {
        this.action.doAction("doorway_agents_dashboard.action_agents_dashboard");
    }

    skipFeedback() {
        this.state.phase = "assist";
    }

    async copyScriptToAgent() {
        if (!this.testCallId) {
            return;
        }
        this.state.busy = true;
        try {
            const res = await this.orm.call(
                "doorway.agent.test.call",
                "web_test_copy_script_to_agent",
                [this.testCallId]
            );
            if (res.ok === false) {
                this.notification.add(res.error || "Copie impossible.", {
                    type: "warning",
                });
                return;
            }
            this.state.scriptIsLinked = false;
            this.state.scriptLabel = "Prompt Odoo — script copié sur cet agent";
            this.notification.add(res.message || "Script copié.", { type: "success" });
            await this.bootstrap();
        } catch (err) {
            this.notification.add(rpcErrorMessage(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    openAgentPrompt() {
        const agentId = this._sessionConfig?.agent_id;
        if (!agentId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.client",
            tag: "agent_wizard_action",
            name: "Modifier le prompt",
            context: {
                default_agent_id: agentId,
                open_wizard_step: "prompt",
            },
        });
    }

    async startCampaign() {
        if (!this.testCallId) {
            return;
        }
        this.state.busy = true;
        try {
            const res = await this.orm.call(
                "doorway.agent.test.call",
                "web_test_go_live",
                [this.testCallId]
            );
            const name = res.campaign_name || "Campagne";
            if (res.started) {
                this.notification.add(`Campagne « ${name} » démarrée.`, {
                    type: "success",
                });
            } else if (res.vicidial_message) {
                this.notification.add(
                    `Campagne « ${name} » prête. VICIdial : ${res.vicidial_message}`,
                    { type: "warning", sticky: true }
                );
            } else {
                this.notification.add(`Campagne « ${name} » prête.`, {
                    type: "success",
                });
            }
            if (res.action) {
                this.action.doAction(res.action);
            }
        } catch (err) {
            this.notification.add(rpcErrorMessage(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async openCampaignConfig() {
        const agentId = this._sessionConfig?.agent_id;
        if (!agentId) {
            this.action.doAction(
                "doorway_vicidial_campaigns.action_campaign_dashboard"
            );
            return;
        }
        this.state.busy = true;
        try {
            const camps = await this.orm.searchRead(
                "doorway.campaign",
                [["ia_agent_id", "=", agentId]],
                ["id", "name"],
                { order: "create_date desc", limit: 1 }
            );
            if (camps.length) {
                this.action.doAction({
                    type: "ir.actions.client",
                    tag: "campaign_dashboard_action",
                    name: camps[0].name,
                    context: { default_campaign_id: camps[0].id },
                });
                return;
            }
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "doorway.campaign",
                views: [[false, "form"]],
                target: "current",
                context: {
                    default_ia_agent_id: agentId,
                    default_campaign_mode: "ia_agent",
                    default_name: `${this.state.agentName || "Agent"} — Production`,
                },
            });
        } catch (err) {
            this.notification.add(rpcErrorMessage(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("agent_web_call_action", AgentWebCall);
