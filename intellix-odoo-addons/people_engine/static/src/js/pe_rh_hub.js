/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const FR_MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];
const CURRENCY_SYMBOLS = { CAD: "$", EUR: "€", MAD: "MAD", USD: "$" };

class PeRhHub extends Component {
    static template = "people_engine.PeRhHub";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: null,
            employee: {},
            performance: {},
            kpis: {},
            perfSeries: [],
            devPlan: {},
            payroll: {},
            legalDocs: [],
            hrDocs: {},
        });
        onMounted(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call("pe.employee.profile", "rh_hub_snapshot", []);
            if (data.error) {
                this.state.error = data.error;
            } else {
                this.state.employee = data.employee || {};
                this.state.performance = data.performance || {};
                this.state.kpis = data.kpis || {};
                this.state.perfSeries = data.perf_series || [];
                this.state.devPlan = data.dev_plan || {};
                this.state.payroll = data.payroll || {};
                this.state.legalDocs = data.legal_docs || [];
                this.state.hrDocs = data.hr_docs || {};
            }
        } catch (err) {
            this.state.error = err?.message || "load_failed";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // ── Identité ──
    get firstName() {
        return (
            this.state.employee.first_name ||
            (this.state.employee.name || "").split(" ")[0] ||
            ""
        );
    }

    get avatarUrl() {
        const id = this.state.employee.id;
        return id ? `/web/image/hr.employee/${id}/avatar_256` : false;
    }

    get initials() {
        const name = (this.state.employee.name || "").trim();
        if (!name) {
            return "RH";
        }
        return name
            .split(/\s+/)
            .slice(0, 2)
            .map((w) => w.charAt(0).toUpperCase())
            .join("");
    }

    // ── KPI (4 cartes du haut) ──
    get leaveLabel() {
        const v = this.state.kpis.leave_remaining;
        return v === null || v === undefined ? "—" : `${Math.round(v)}`;
    }

    get hoursLabel() {
        const v = this.state.kpis.hours_month;
        return v === null || v === undefined ? "—" : `${Math.round(v)}h`;
    }

    get scoreLabel() {
        const v = this.state.kpis.score_percent;
        return v === null || v === undefined ? "—" : `${Math.round(v)}%`;
    }

    get nextEvalLabel() {
        const iso = this.state.kpis.next_eval;
        if (!iso) {
            return "À planifier";
        }
        const d = new Date(`${iso}T00:00:00`);
        if (Number.isNaN(d.getTime())) {
            return "À planifier";
        }
        return `${d.getDate()} ${FR_MONTHS[d.getMonth()]}`;
    }

    // ── Performance (area chart) ──
    get perfChart() {
        const pts = this.state.perfSeries || [];
        const W = 100;
        const H = 40;
        const pad = 4;
        if (pts.length < 2) {
            return { hasData: false, line: "", area: "" };
        }
        const n = pts.length;
        const coords = pts.map((p, i) => {
            const value = Math.min(100, Math.max(0, Number(p.value) || 0));
            const x = (i / (n - 1)) * W;
            const y = H - pad - (value / 100) * (H - pad * 2);
            return [Number(x.toFixed(2)), Number(y.toFixed(2))];
        });
        const line = coords.map((c) => c.join(",")).join(" ");
        const first = coords[0];
        const last = coords[coords.length - 1];
        const area = `${first[0]},${H} ${line} ${last[0]},${H}`;
        return { hasData: true, line, area };
    }

    // ── Plan de développement ──
    get devItems() {
        return this.state.devPlan.items || [];
    }

    // ── Paie ──
    get payrollLabel() {
        const p = this.state.payroll || {};
        if (p.net === null || p.net === undefined) {
            return null;
        }
        const amount = Math.round(p.net).toLocaleString("fr-FR");
        const sym = CURRENCY_SYMBOLS[p.currency] || p.currency || "";
        return `${amount} ${sym}`.trim();
    }

    get hasPayslip() {
        return Boolean(this.state.payroll && this.state.payroll.has_payslip);
    }

    // ── Documents légaux ──
    get legalDocs() {
        return this.state.legalDocs || [];
    }

    // ── Actions / navigation (handlers existants préservés) ──
    openDashboardEmployee() {
        this.action.doAction("people_engine.action_dashboard_employee");
    }

    openTraining() {
        const xmlid = "people_engine.action_pe_course";
        this.action.doAction(xmlid).catch(() => {
            this.action.doAction("people_engine.action_dashboard_employee");
        });
    }

    async openPayslip() {
        try {
            const action = await this.orm.call("pe.payslip.live", "action_open_my_payslip", []);
            if (action && action.type) {
                this.action.doAction(action);
            }
        } catch (err) {
            this.notification.add("Fiche de paie indisponible pour le moment.", {
                type: "warning",
            });
        }
    }

    openManagementReview() {
        this.openDashboardEmployee();
    }
}

registry.category("actions").add("pe_rh_hub_action", PeRhHub);

// ════════════════════════════════════════════════════════════════════
// Vue d'ensemble RH (superviseur / global) — même langage visuel que le
// hub personnel, mais agrège des KPI temps réel à l'échelle de l'équipe
// (portée déterminée par les ir.rule : RH/admin = entreprise, gestionnaire
// = équipe directe).
// ════════════════════════════════════════════════════════════════════
class PeRhGlobal extends Component {
    static template = "people_engine.PeRhGlobal";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: null,
            empty: false,
            scope: "",
            kpis: {},
            bands: [],
            trends: {},
            training: {},
            payroll: {},
            scoreBars: [],
            topPerformers: [],
            leaderSort: "score",
        });
        onMounted(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call(
                "pe.employee.profile",
                "rh_global_snapshot",
                [],
                {}
            );
            if (data.error) {
                this.state.error = data.error;
            } else if (!data.headcount) {
                this.state.empty = true;
            } else {
                this.state.empty = false;
                this.state.scope = data.scope || "";
                this.state.kpis = data.kpis || {};
                this.state.bands = data.bands || [];
                this.state.trends = data.trends || {};
                this.state.training = data.training || {};
                this.state.payroll = data.payroll || {};
                this.state.scoreBars = data.score_bars || [];
                this.state.topPerformers = data.top_performers || [];
            }
        } catch (err) {
            this.state.error = err?.message || "load_failed";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    get scopeLabel() {
        return this.state.scope === "hr"
            ? "Vue entreprise — tous les collaborateurs"
            : "Vue équipe — collaborateurs directs";
    }

    get avgScoreLabel() {
        const v = this.state.kpis.avg_score;
        return v === null || v === undefined ? "—" : `${Math.round(v)}%`;
    }

    get payrollLabel() {
        const p = this.state.payroll || {};
        if (!p.has_data) {
            return null;
        }
        const amount = Math.round(p.net || 0).toLocaleString("fr-FR");
        const sym = CURRENCY_SYMBOLS[p.currency] || p.currency || "";
        return `${amount} ${sym}`.trim();
    }

    initialsOf(name) {
        const n = (name || "").trim();
        if (!n) {
            return "—";
        }
        return n
            .split(/\s+/)
            .slice(0, 2)
            .map((w) => w.charAt(0).toUpperCase())
            .join("");
    }

    avatarOf(id) {
        return id ? `/web/image/hr.employee/${id}/avatar_128` : false;
    }

    openPersonalHub() {
        this.action.doAction("people_engine.action_pe_rh_hub");
    }

    openTeamDetail() {
        this.action.doAction("people_engine.action_dashboard_manager");
    }

    openHrDashboard() {
        this.action.doAction("people_engine.action_pe_hr_dashboard").catch(() => {
            this.action.doAction("people_engine.action_dashboard_manager");
        });
    }


    get sortedTopPerformers() {
        const rows = [...(this.state.topPerformers || [])];
        if (this.state.leaderSort === "name") {
            rows.sort((a, b) => (a.name || "").localeCompare(b.name || "", "fr"));
        } else {
            rows.sort((a, b) => (b.score || 0) - (a.score || 0));
        }
        return rows;
    }

    toggleLeaderSort() {
        this.state.leaderSort = this.state.leaderSort === "score" ? "name" : "score";
    }

    async generatePayrollBulletins() {
        try {
            const count = await this.orm.call(
                "pe.payroll.bulletin",
                "generer_bulletins_periode_courante",
                []
            );
            this.notification.add(
                count ? `${count} bulletin(s) généré(s).` : "Aucun bulletin à générer.",
                { type: count ? "success" : "info" }
            );
            await this.load();
        } catch (err) {
            this.notification.add("Génération bulletins indisponible.", { type: "warning" });
        }
    }

    openEvaluations() {
        this.action.doAction("people_engine.action_pe_evaluation").catch(() => {});
    }
}

registry.category("actions").add("pe_rh_global_action", PeRhGlobal);
