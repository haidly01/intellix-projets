/** @odoo-module **/

import { Component, onMounted, onPatched, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpcErrorMessage } from "./rpc_error";

const PIPELINE_LABELS = {
    renovation: "Rénovation",
    immobilier: "Immobilier",
    marketing: "Marketing",
    driven: "Driven",
    assurance: "Assurance",
    doorway: "Doorway",
};

const TYPE_LABELS = {
    inbound: "Entrant",
    outbound: "Sortant",
    followup: "Suivi automatique",
};

const ROLE_HINTS = {
    inbound: "Qualification & accueil",
    outbound: "Génération de leads",
    followup: "Suivi automatique",
};

const SPARK_COLOR = "#7F77DD";
const SPARK_FILL = "rgba(127, 119, 221, 0.18)";

function drawSparkline(canvas, values) {
    if (!canvas) {
        return;
    }
    const data = values && values.length ? values : [0, 0, 0, 0, 0, 0, 0];
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.parentElement?.clientWidth || 280;
    const height = 56;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const pad = { l: 4, r: 4, t: 8, b: 8 };
    const chartW = width - pad.l - pad.r;
    const chartH = height - pad.t - pad.b;
    const maxVal = Math.max(1, ...data);
    const step = chartW / Math.max(1, data.length - 1);

    ctx.beginPath();
    data.forEach((val, idx) => {
        const x = pad.l + idx * step;
        const y = pad.t + chartH - (val / maxVal) * chartH;
        if (idx === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.lineTo(pad.l + (data.length - 1) * step, pad.t + chartH);
    ctx.lineTo(pad.l, pad.t + chartH);
    ctx.closePath();
    ctx.fillStyle = SPARK_FILL;
    ctx.fill();

    ctx.beginPath();
    data.forEach((val, idx) => {
        const x = pad.l + idx * step;
        const y = pad.t + chartH - (val / maxVal) * chartH;
        if (idx === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.strokeStyle = SPARK_COLOR;
    ctx.lineWidth = 2;
    ctx.stroke();
}

class AgentsDashboard extends Component {
    static template = "doorway_agents_dashboard.AgentsDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.syncAgents = this.syncAgents.bind(this);
        this.openTestWizard = this.openTestWizard.bind(this);
        this.openWebTest = this.openWebTest.bind(this);
        this.openCreateWizard = this.openCreateWizard.bind(this);
        this.openEditWizard = this.openEditWizard.bind(this);
        this.openTelephonyWizard = this.openTelephonyWizard.bind(this);
        this.archiveAgent = this.archiveAgent.bind(this);
        this.deleteAgent = this.deleteAgent.bind(this);
        this.openHistory = this.openHistory.bind(this);
        this.setFilter = this.setFilter.bind(this);
        this.setStatusFilter = this.setStatusFilter.bind(this);
        this.selectAgent = this.selectAgent.bind(this);
        this.sparklineTotal = this.sparklineTotal.bind(this);
        this.pipelineLabel = this.pipelineLabel.bind(this);
        this.state = useState({
            agents: [],
            optimalAgents: [],
            newAgents: [],
            selectedAgentId: null,
            filters: {
                provider: "all",
                pipeline: "all",
                agent_type: "all",
                status: "active",
            },
            globalKpis: {
                success_rate: 0,
                latency_ms: 0,
                calls_24h: 0,
            },
            loading: true,
        });
        this.refreshInterval = null;
        onMounted(() => {
            this.loadAgents();
            this.refreshInterval = setInterval(() => this.loadAgents(), 300000);
        });
        onPatched(() => {
            if (!this.state.loading) {
                this._renderSparklines();
            }
        });
        onWillUnmount(() => {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
        });
    }

    _renderSparklines() {
        const byId = Object.fromEntries(
            this.state.agents.map((a) => [String(a.id), a.sparkline || []])
        );
        for (const canvas of document.querySelectorAll(".ix-dash-sparkline")) {
            const id = canvas.getAttribute("data-agent-id");
            drawSparkline(canvas, byId[id] || []);
        }
    }

    async loadAgents() {
        this.state.loading = true;
        try {
            const payload = await this.orm.call(
                "doorway.agent.profile",
                "get_agents_ia_dashboard",
                [this.state.filters]
            );
            this.state.agents = payload.agents || [];
            this.state.optimalAgents = payload.optimal_agents || [];
            this.state.newAgents = payload.new_agents || [];
            this.state.globalKpis = payload.global_kpis || {
                success_rate: 0,
                latency_ms: 0,
                calls_24h: 0,
            };
            if (
                this.state.agents.length &&
                !this.state.agents.some((a) => a.id === this.state.selectedAgentId)
            ) {
                const firstActive =
                    this.state.agents.find((a) => a.status === "active") ||
                    this.state.agents[0];
                this.state.selectedAgentId = firstActive.id;
            } else if (!this.state.agents.length) {
                this.state.selectedAgentId = null;
            }
        } catch (error) {
            console.error("AgentsDashboard.loadAgents", error);
            this.notification.add(
                error.message || "Impossible de charger les agents.",
                { type: "danger" }
            );
            this.state.agents = [];
            this.state.optimalAgents = [];
            this.state.newAgents = [];
        } finally {
            this.state.loading = false;
        }
    }

    setFilter(key, value) {
        this.state.filters[key] = value;
        this.loadAgents();
    }

    setStatusFilter(status) {
        this.state.filters.status = status;
        this.loadAgents();
    }

    selectAgent(agentId) {
        this.state.selectedAgentId = agentId;
    }

    sparklineTotal(agent) {
        const vals = agent.sparkline || [];
        return vals.reduce((s, v) => s + (v || 0), 0);
    }

    pipelineLabel(code) {
        return PIPELINE_LABELS[code] || code;
    }

    agentSubtitle(agent) {
        const hint = ROLE_HINTS[agent.agent_type];
        const pipeline = PIPELINE_LABELS[agent.pipeline] || agent.pipeline;
        if (hint) {
            return `${hint} · ${pipeline}`;
        }
        const typeLabel = TYPE_LABELS[agent.agent_type] || agent.agent_type;
        return `${typeLabel} · ${pipeline}`;
    }

    statusPillClass(status) {
        if (status === "active") {
            return "ix-dash-status ix-dash-status--active";
        }
        if (status === "error") {
            return "ix-dash-status ix-dash-status--error";
        }
        return "ix-dash-status ix-dash-status--pause";
    }

    statusPillLabel(status) {
        if (status === "active") {
            return "ACTIF";
        }
        if (status === "error") {
            return "ERREUR";
        }
        return "EN PAUSE";
    }

    labelProvider(code) {
        return code === "elevenlabs" ? "ElevenLabs" : code === "n8n" ? "n8n" : code;
    }

    async syncAgents() {
        await this.orm.call("doorway.agent.profile", "cron_sync_agents", []);
        this.notification.add("Synchronisation ElevenLabs / n8n terminée.", {
            type: "success",
        });
        await this.loadAgents();
    }

    openCreateWizard() {
        this.action.doAction("doorway_agents_dashboard.action_agent_wizard");
    }

    openEditWizard(agentId) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "agent_wizard_action",
            name: "Modifier l'agent",
            context: { default_agent_id: agentId },
        });
    }

    openTelephonyWizard(agentId) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "agent_wizard_action",
            name: "Téléphonie",
            context: {
                default_agent_id: agentId,
                open_wizard_step: "telephony",
            },
        });
    }

    async archiveAgent(agentId, agentName) {
        const ok = window.confirm(
            `Mettre l'agent « ${agentName} » en pause ?\n\nL'agent restera en base mais ne sera plus actif.`
        );
        if (!ok) {
            return;
        }
        try {
            await this.orm.call(
                "doorway.agent.profile",
                "action_archive_agent",
                [[agentId]]
            );
            this.notification.add("Agent mis en pause.", { type: "success" });
            await this.loadAgents();
        } catch (error) {
            this.notification.add(error.message || "Erreur archivage.", {
                type: "danger",
            });
        }
    }

    async deleteAgent(agentId, agentName) {
        const releaseTwilio = window.confirm(
            `Supprimer définitivement « ${agentName} » ?\n\n` +
                "Cliquez OK pour supprimer. Les numéros Twilio achetés via Odoo " +
                "ne seront PAS libérés automatiquement.\n\n" +
                "Pour libérer aussi les numéros Twilio achetés, confirmez une seconde fois."
        );
        if (!releaseTwilio) {
            return;
        }
        const doRelease = window.confirm(
            "Libérer également les numéros achetés via Twilio sur ce compte ?"
        );
        try {
            await this.orm.call(
                "doorway.agent.profile",
                "action_delete_agent",
                [[agentId]],
                { release_twilio: doRelease }
            );
            this.notification.add("Agent supprimé.", { type: "success" });
            this.state.selectedAgentId = null;
            await this.loadAgents();
        } catch (error) {
            this.notification.add(rpcErrorMessage(error) || "Suppression impossible.", {
                type: "danger",
            });
        }
    }

    openTestWizard(agentId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "doorway.test.call.wizard",
            views: [[false, "form"]],
            target: "new",
            context: { default_agent_id: agentId },
        });
    }

    async openWebTest(agentId) {
        const callOpen = () =>
            this.orm.call(
                "doorway.agent.profile",
                "action_open_web_test",
                [[agentId]]
            );
        try {
            let action;
            try {
                action = await callOpen();
            } catch (firstError) {
                const msg = firstError?.message || "";
                if (
                    msg.includes("couldn't be established") ||
                    msg.includes("interrupted") ||
                    msg.includes("Failed to fetch")
                ) {
                    await new Promise((r) => setTimeout(r, 1500));
                    action = await callOpen();
                } else {
                    throw firstError;
                }
            }
            this.action.doAction(action);
        } catch (error) {
            this.notification.add(
                rpcErrorMessage(error) ||
                    "Test web indisponible. Rechargez la page (Ctrl+F5) puis réessayez.",
                { type: "danger" }
            );
        }
    }

    openHistory(agentId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Appels test",
            res_model: "doorway.agent.test.call",
            views: [[false, "list"], [false, "form"]],
            domain: [["agent_id", "=", agentId]],
            target: "current",
        });
    }
}

registry.category("actions").add("agents_dashboard_action", AgentsDashboard);
registry.category("actions").add("doorway_agents_dashboard", AgentsDashboard);
