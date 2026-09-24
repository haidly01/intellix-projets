/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { onWillStart, useState } from "@odoo/owl";
import {
    scoreColor,
    initials,
    avatarColor,
    trendClass,
    trendLabel,
} from "./team_dashboard_utils";
import { employeesByBand, bandStats } from "./team_dashboard";

const PERIOD_OPTIONS = [7, 30, 90];

export class PeopleEngineTeamListController extends ListController {
    static template = "people_engine.TeamListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.teamDash = useState({
            loaded: false,
            periodDays: 30,
            kanbanLoaded: false,
            kanbanEmployees: [],
            data: {
                kpis: {},
                leaderboard: [],
                alerts: [],
                status_distrib: [],
                onboarding_pipeline: [],
                primes_due: [],
                score_chart: [],
                filter_counts: {},
                period_days: 30,
                period_label: "30j",
            },
            activeFilter: "all",
        });
        onWillStart(async () => {
            await this.loadDashboard();
        });
    }

    async loadDashboard() {
        const periodDays = this.teamDash.periodDays;
        const [data, employees] = await Promise.all([
            this.orm.call("pe.employee.profile", "get_team_dashboard_data", [], {
                period_days: periodDays,
            }),
            this.orm.call("pe.employee.profile", "get_team_kanban_employees", []),
        ]);
        this.teamDash.data = data;
        this.teamDash.kanbanEmployees = employees;
        this.teamDash.loaded = true;
        this.teamDash.kanbanLoaded = true;
    }

    async onPeriodChange(ev) {
        const days = parseInt(ev.currentTarget.dataset.period, 10);
        if (!PERIOD_OPTIONS.includes(days) || days === this.teamDash.periodDays) {
            return;
        }
        this.teamDash.periodDays = days;
        this.teamDash.loaded = false;
        const baseCtx = this.model?.config?.context || this.props.context || {};
        const ctx = { ...baseCtx, pe_team_period_days: days };
        if (this.model?.config) {
            this.model.config.context = ctx;
        }
        await this.loadDashboard();
        if (this.model?.root?.load) {
            await this.model.root.load();
        }
    }

    periodBtnClass(days) {
        return this.teamDash.periodDays === days
            ? "pe-team-period-btn pe-team-period-btn-active"
            : "pe-team-period-btn";
    }

    async onRefreshDashboard() {
        this.teamDash.loaded = false;
        await this.loadDashboard();
        if (this.model?.root?.load) {
            await this.model.root.load();
        }
    }

    async onNewEmployee() {
        await this.actionService.doAction("people_engine.action_pe_invite_collaborator");
    }

    async onCoachingTeam() {
        await this.actionService.doAction("people_engine.action_pe_coaching_sessions");
    }

    async onRefreshScores() {
        await this.actionService.doAction("people_engine.action_pe_score_refresh_wizard");
    }

    async onExport() {
        const action = await this.orm.call(
            "pe.employee.profile",
            "action_export_team_dashboard_csv",
            [],
            { period_days: this.teamDash.periodDays }
        );
        if (action) {
            await this.actionService.doAction(action);
        }
    }

    async onFilterChip(ev) {
        const filter = ev.currentTarget.dataset.filter;
        if (!filter || !this.env.searchModel) {
            return;
        }
        this.teamDash.activeFilter = filter;
        const mapping = {
            all: null,
            monitoring: "monitoring",
            essai: "stage_probation",
            inactif: "inactive",
        };
        const searchModel = this.env.searchModel;
        for (const item of searchModel.searchItems) {
            if (item.type === "filter" && searchModel.query.find((q) => q.searchItemId === item.id)) {
                searchModel.toggleSearchItem(item.id);
            }
        }
        const name = mapping[filter];
        if (name) {
            const item = searchModel.searchItems.find((i) => i.name === name);
            if (item) {
                searchModel.toggleSearchItem(item.id);
            }
        }
    }

    chipClass(filter) {
        return this.teamDash.activeFilter === filter ? "pe-team-chip pe-team-chip-active" : "pe-team-chip";
    }

    async openRecord(record, opts = {}) {
        const action = {
            type: "ir.actions.act_window",
            res_model: "pe.employee.profile",
            res_id: record.resId,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
            context: {
                ...this.props.context,
                form_view_ref: "people_engine.view_pe_employee_profile_form_mockup",
            },
        };
        await this.actionService.doAction(action);
    }

    async onAlertClick(alert) {
        if (alert.profile_id) {
            await this.openRecord({ resId: alert.profile_id, resModel: "pe.employee.profile" });
        }
    }

    async onLeaderClick(entry) {
        if (entry.profile_id) {
            await this.openRecord({ resId: entry.profile_id, resModel: "pe.employee.profile" });
        }
    }

    get kanbanBands() {
        return employeesByBand(this.teamDash.kanbanEmployees);
    }

    get kanbanStats() {
        return bandStats(this.teamDash.kanbanEmployees);
    }

    scoreColor(score) {
        return scoreColor(score);
    }

    initials(name) {
        return initials(name);
    }

    avatarColor(id) {
        return avatarColor(id);
    }

    trendClass(trend) {
        return trendClass(trend);
    }

    trendLabel(trend) {
        return trendLabel(trend);
    }

    formatScore(score) {
        return Math.round(score || 0);
    }

    get bandDefs() {
        return [
            { key: "watch", title: "À surveiller (<60)", empty: "Aucun agent à surveiller" },
            { key: "growing", title: "En progression (60–80)", empty: "Aucun agent en progression" },
            { key: "top", title: "Performants (>80)", empty: "Aucun performant" },
        ];
    }

    async onKanbanEmployeeClick(emp) {
        if (emp.pe_profile_id) {
            await this.openRecord({
                resId: emp.pe_profile_id,
                resModel: "pe.employee.profile",
            });
        }
    }
}

export const peopleEngineTeamListView = {
    ...listView,
    Controller: PeopleEngineTeamListController,
};

registry.category("views").add("people_engine_team_dashboard", peopleEngineTeamListView);
