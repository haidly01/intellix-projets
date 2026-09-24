/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

function todayIso() {
    return new Date().toISOString().slice(0, 10);
}

function daysAgoIso(days) {
    const d = new Date();
    d.setDate(d.getDate() - days);
    return d.toISOString().slice(0, 10);
}

class MyCoachingDashboard extends Component {
    static template = "doorway_vicidial_campaigns.MyCoachingDashboard";

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            period: "30",
            dateFrom: daysAgoIso(30),
            dateTo: todayIso(),
            employeeName: "",
            calls: [],
            sessions: [],
            plans: [],
            kpis: {},
            criteriaAverages: [],
            insights: {},
            gamification: {},
            selectedCallId: null,
        });
        onMounted(() => this.load());
    }

    get selectedCall() {
        if (!this.state.selectedCallId) {
            return this.state.calls[0] || null;
        }
        return (
            this.state.calls.find((c) => c.id === this.state.selectedCallId) ||
            this.state.calls[0] ||
            null
        );
    }

    formatCallDate(value) {
        if (!value) {
            return "—";
        }
        const d = new Date(value.replace(" ", "T"));
        if (Number.isNaN(d.getTime())) {
            return value.slice(0, 16).replace("T", " · ");
        }
        const months = [
            "jan", "fév", "mar", "avr", "mai", "juin",
            "juil", "aoû", "sep", "oct", "nov", "déc",
        ];
        const day = d.getDate();
        const month = months[d.getMonth()];
        const hours = String(d.getHours()).padStart(2, "0");
        const mins = String(d.getMinutes()).padStart(2, "0");
        return `${day} ${month} · ${hours}h${mins}`;
    }

    formatDetailMeta(call) {
        if (!call) {
            return "";
        }
        const parts = [
            this.formatCallDate(call.date_appel),
            call.duree,
        ];
        if (call.lead_subtitle) {
            parts.push(call.lead_subtitle);
        }
        if (call.qualification_label) {
            parts.push(call.qualification_label);
        }
        return parts.filter(Boolean).join(" · ");
    }

    scoreClass(score) {
        if (score >= 85) {
            return "o_mc_score-excellent";
        }
        if (score >= 70) {
            return "o_mc_score-good";
        }
        if (score >= 55) {
            return "o_mc_score-medium";
        }
        return "o_mc_score-low";
    }

    scoreIcon(score) {
        if (score >= 85) {
            return "✦";
        }
        if (score >= 70) {
            return "◆";
        }
        if (score >= 55) {
            return "▲";
        }
        return "✕";
    }

    statusClass(qual) {
        const map = {
            qualifie: "o_mc_status-qualifie",
            rdv: "o_mc_status-qualifie",
            b2b_valide: "o_mc_status-qualifie",
            a_rappeler: "o_mc_status-rappel",
            pas_interesse: "o_mc_status-pas-int",
            deja_servi: "o_mc_status-pas-int",
            dnc: "o_mc_status-pas-int",
            messagerie: "o_mc_status-nrp",
            non_fait: "o_mc_status-nrp",
            hors_cible: "o_mc_status-nrp",
            locataire: "o_mc_status-nrp",
            faux_num: "o_mc_status-nrp",
        };
        return map[qual] || "o_mc_status-nrp";
    }

    statusPrefix(qual) {
        const map = {
            qualifie: "●",
            rdv: "●",
            b2b_valide: "●",
            a_rappeler: "◑",
            pas_interesse: "✕",
            messagerie: "○",
            non_fait: "○",
        };
        return map[qual] || "○";
    }

    insightsLabel(call) {
        if (!call.analyse_done && !call.insights_count) {
            return { text: "—", className: "" };
        }
        if (call.needs_review && !call.lu_par_employe) {
            return { text: "⚠ À réviser", className: "warn" };
        }
        if (call.points_ameliorer && call.score_global < 60) {
            return { text: "⚠ Objection manquée", className: "danger" };
        }
        const n = call.insights_count || 1;
        return { text: `🤖 ${n} insight${n > 1 ? "s" : ""}`, className: "" };
    }

    criterionColor(score) {
        if (score >= 80) {
            return "#10b981";
        }
        if (score >= 65) {
            return "#6366f1";
        }
        return "#f59e0b";
    }

    kpiBarWidth(value, max = 100) {
        return `${Math.min(Math.round((value / max) * 100), 100)}%`;
    }

    async load() {
        this.state.loading = true;
        try {
            const url =
                `/doorway/vicidial/coaching/my?date_from=${this.state.dateFrom}` +
                `&date_to=${this.state.dateTo}`;
            const response = await fetch(url, { credentials: "same-origin" });
            if (!response.ok) {
                throw new Error("load_failed");
            }
            const data = await response.json();
            this.state.employeeName = data.employee_name || "";
            this.state.calls = data.calls || [];
            this.state.sessions = data.sessions || [];
            this.state.plans = data.plans || [];
            this.state.kpis = data.kpis || {};
            this.state.criteriaAverages = data.criteria_averages || [];
            this.state.insights = data.insights || {};
            this.state.gamification = data.gamification || {};
            if (
                this.state.selectedCallId &&
                !this.state.calls.some((c) => c.id === this.state.selectedCallId)
            ) {
                this.state.selectedCallId = null;
            }
            if (!this.state.selectedCallId && this.state.calls.length) {
                this.state.selectedCallId = this.state.calls[0].id;
            }
        } catch (_e) {
            this.notification.add("Impossible de charger votre coaching.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    setPeriod(days) {
        this.state.period = String(days);
        if (days === "all") {
            this.state.dateFrom = "2020-01-01";
            this.state.dateTo = todayIso();
        } else {
            this.state.dateFrom = daysAgoIso(Number(days));
            this.state.dateTo = todayIso();
        }
        this.load();
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.state.period = "custom";
        this.load();
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.state.period = "custom";
        this.load();
    }

    selectCall(callId, ev) {
        if (ev && ev.target.closest("a, button")) {
            return;
        }
        this.state.selectedCallId = callId;
        const call = this.state.calls.find((c) => c.id === callId);
        if (call && !call.lu_par_employe) {
            this.markRead(callId, true);
        }
    }

    async markRead(callId, silent = false) {
        const response = await fetch(
            `/doorway/vicidial/coaching/mark_read/${callId}`,
            { method: "POST", credentials: "same-origin" }
        );
        if (response.ok) {
            const call = this.state.calls.find((c) => c.id === callId);
            if (call) {
                call.lu_par_employe = true;
                if (this.state.kpis.unread > 0) {
                    this.state.kpis.unread -= 1;
                }
            }
            if (!silent) {
                await this.load();
            }
        }
    }

    openLead(leadId, ev) {
        ev.stopPropagation();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "crm.lead",
            res_id: leadId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }

    openTeamDashboard() {
        this.action.doAction("doorway_vicidial_campaigns.action_calls_coaching_dashboard");
    }

    exportPdf() {
        window.print();
    }

    isPeriodActive(days) {
        return this.state.period === String(days);
    }

    analysisCoveragePct() {
        const total = this.state.kpis.total || 0;
        if (!total) {
            return 0;
        }
        return Math.round((this.state.kpis.analysed / total) * 100);
    }

    objectivePct(pct) {
        return Math.min(pct || 0, 100);
    }
}

registry.category("actions").add(
    "my_coaching_dashboard_action",
    MyCoachingDashboard
);
