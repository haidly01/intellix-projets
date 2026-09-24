/** @odoo-module **/



import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";

import { registry } from "@web/core/registry";

import { useService } from "@web/core/utils/hooks";



const POLL_MS = 8000;



function todayIso() {

    return new Date().toISOString().slice(0, 10);

}



function daysAgoIso(days) {

    const d = new Date();

    d.setDate(d.getDate() - days);

    return d.toISOString().slice(0, 10);

}



class VicidialQualificationHub extends Component {

    static template = "doorway_vicidial_campaigns.VicidialQualificationHub";



    setup() {

        this.action = useService("action");

        this.notification = useService("notification");

        this.busService = useService("bus_service");

        this.leadSync = useService("doorway_vicidial_lead_sync");

        this.pollTimer = null;

        this.state = useState({

            loading: true,

            silentRefresh: false,

            activeTab: "dashboard",

            dateFrom: daysAgoIso(7),

            dateTo: todayIso(),

            activeCampaign: "all",

            activeCampaignState: "all",

            campaignOptions: [],

            campaignStates: [],

            isSupervisor: false,

            refreshedAt: "",

            liveCall: null,

            campaigns: [],

            statusColumns: [],

            queue: { total: 0, pending: 0, leads: [] },

            dashboard: { kpi_cards: [], rows: [] },

            supervision: null,

        });

        onMounted(() => {

            if (this.leadSync.setSessionActive) {

                this.leadSync.setSessionActive(true);

            }

            this.load();

            this.pollTimer = setInterval(() => this.load(true), POLL_MS);

            this.busService.subscribe(

                "doorway/vicidial/qualification_updated",

                () => this.load(true)

            );

            this.busService.subscribe("doorway/vicidial/lead_open", () =>

                this.load(true)

            );

            this.busService.subscribe("doorway/vicidial/call_ended", () =>

                this.load(true)

            );

        });

        onWillUnmount(() => {

            if (this.pollTimer) {

                clearInterval(this.pollTimer);

            }

            if (this.leadSync.setSessionActive) {

                this.leadSync.setSessionActive(false);

            }

        });

    }



    applyData(data) {

        this.state.isSupervisor = !!data.is_supervisor;

        this.state.refreshedAt = data.refreshed_at || "";

        this.state.liveCall = data.live_call || null;

        this.state.campaigns = data.campaigns || [];

        this.state.statusColumns = data.status_columns || [];

        this.state.campaignOptions = data.campaign_options || [];

        this.state.campaignStates = data.campaign_states || [];

        this.state.queue = data.queue || this.state.queue;

        this.state.dashboard = data.dashboard || this.state.dashboard;

        this.state.supervision = data.supervision || null;

    }



    async load(silent = false) {

        if (!silent) {

            this.state.loading = true;

        } else {

            this.state.silentRefresh = true;

        }

        try {

            const url =

                `/doorway/vicidial/qualification/hub?date_from=${this.state.dateFrom}` +

                `&date_to=${this.state.dateTo}` +

                `&campaign_vicidial_id=${encodeURIComponent(this.state.activeCampaign)}` +

                `&campaign_state=${encodeURIComponent(this.state.activeCampaignState)}`;

            const response = await fetch(url, { credentials: "same-origin" });

            if (!response.ok) {

                throw new Error("load_failed");

            }

            this.applyData(await response.json());

        } catch (_e) {

            if (!silent) {

                this.notification.add("Impossible de charger Qualification CRM.", {

                    type: "danger",

                });

            }

        } finally {

            this.state.loading = false;

            this.state.silentRefresh = false;

        }

    }



    setTab(tab) {

        this.state.activeTab = tab;

    }



    onDateFromChange(ev) {

        this.state.dateFrom = ev.target.value;

        this.load();

    }



    onDateToChange(ev) {

        this.state.dateTo = ev.target.value;

        this.load();

    }



    onCampaignChange(ev) {

        this.state.activeCampaign = ev.target.value || "all";

        this.load();

    }



    onCampaignStateChange(ev) {

        this.state.activeCampaignState = ev.target.value || "all";

        this.load();

    }



    campaignStateBadge(state) {

        const map = {

            active: "text-bg-success",

            paused: "text-bg-warning",

            ready: "text-bg-info",

            draft: "text-bg-secondary",

            completed: "text-bg-dark",

            cancelled: "text-bg-danger",

        };

        return map[state] || "text-bg-secondary";

    }



    statusCount(camp, key) {

        if (!camp || !camp.statuses) {

            return 0;

        }

        return camp.statuses[key] || 0;

    }



    openQueue() {

        this.action.doAction("doorway_vicidial_campaigns.action_vicidial_qualification");

    }



    openGlobalDashboard() {

        this.action.doAction("doorway_vicidial_campaigns.action_calls_coaching_dashboard");

    }



    openSupervisorDashboard() {

        this.action.doAction("doorway_vicidial_campaigns.action_supervisor_dashboard");

    }



    openCampaign(odooCampaignId) {

        if (!odooCampaignId) {

            return;

        }

        this.action.doAction({

            type: "ir.actions.act_window",

            res_model: "doorway.campaign",

            res_id: odooCampaignId,

            view_mode: "form",

            views: [[false, "form"]],

            target: "current",

        });

    }



    openLead(leadId) {

        if (!leadId) {

            return;

        }

        this.action.doAction({

            type: "ir.actions.act_window",

            res_model: "crm.lead",

            res_id: leadId,

            view_mode: "form",

            views: [[false, "form"]],

            target: "current",

        });

    }



    formatDuration(seconds) {

        const s = Number(seconds) || 0;

        const h = Math.floor(s / 3600);

        const m = Math.floor((s % 3600) / 60);

        return `${h}h${String(m).padStart(2, "0")}`;

    }



    formatRefreshedAt(value) {

        if (!value) {

            return "";

        }

        return value.replace("T", " ").slice(0, 19);

    }

}



registry.category("actions").add(

    "vicidial_qualification_hub_action",

    VicidialQualificationHub

);

