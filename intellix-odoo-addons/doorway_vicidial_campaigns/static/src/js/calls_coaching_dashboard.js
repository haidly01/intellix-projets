/** @odoo-module **/



import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";

import { registry } from "@web/core/registry";

import { useService } from "@web/core/utils/hooks";



const POLL_MS = 10000;



const QUALIFICATION_FILTERS = [

    { id: "all", label: "Tous" },

    { id: "pas_interesse", label: "Pas intéressé" },

    { id: "deja_servi", label: "Déjà servi" },

    { id: "locataire", label: "Locataire" },

    { id: "a_rappeler", label: "Rappel" },

    { id: "rdv", label: "RDV" },

    { id: "dnc", label: "DNC" },

    { id: "messagerie", label: "Boîte vocale" },

    { id: "qualifie", label: "Qualifié" },

];



function todayIso() {

    return new Date().toISOString().slice(0, 10);

}



function daysAgoIso(days) {

    const d = new Date();

    d.setDate(d.getDate() - days);

    return d.toISOString().slice(0, 10);

}



class CallsCoachingDashboard extends Component {

    static template = "doorway_vicidial_campaigns.CallsCoachingDashboard";



    setup() {

        this.action = useService("action");

        this.notification = useService("notification");

        this.busService = useService("bus_service");

        this.pollTimer = null;

        this.state = useState({

            loading: true,

            silentRefresh: false,

            dateFrom: daysAgoIso(7),

            dateTo: todayIso(),

            activeQualification: "all",

            qualificationFilters: QUALIFICATION_FILTERS,

            activeCampaign: "all",

            activeCampaignState: "all",

            campaigns: [],

            campaignStates: [],

            rows: [],

            kpis: {},

            kpiCards: [],

        });

        onMounted(() => {

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

        });

    }



    formatDate(value) {

        if (!value) {

            return "—";

        }

        return value.replace("T", " ").slice(0, 16);

    }



    buildKpiCards(kpis) {

        const labels = {

            total: "Total appels",

            pas_interesse: "Pas intéressé",

            deja_servi: "Déjà servi",

            locataire: "Locataire",

            a_rappeler: "Rappel",

            rdv: "RDV",

            dnc: "DNC",

            messagerie: "Boîte vocale",

            qualifie: "Qualifié",

        };

        return Object.keys(labels).map((key) => ({

            key,

            label: labels[key],

            value: kpis[key] || 0,

        }));

    }



    async load(silent = false) {

        if (!silent) {

            this.state.loading = true;

        } else {

            this.state.silentRefresh = true;

        }

        try {

            const quals =

                this.state.activeQualification === "all"

                    ? "all"

                    : this.state.activeQualification;

            const url =

                `/doorway/vicidial/calls/dashboard?date_from=${this.state.dateFrom}` +

                `&date_to=${this.state.dateTo}&qualifications=${quals}` +

                `&campaign_vicidial_id=${encodeURIComponent(this.state.activeCampaign)}` +

                `&campaign_state=${encodeURIComponent(this.state.activeCampaignState)}`;

            const response = await fetch(url, { credentials: "same-origin" });

            if (!response.ok) {

                throw new Error("load_failed");

            }

            const data = await response.json();

            this.state.rows = data.rows || [];

            this.state.kpis = data.kpis || {};

            this.state.kpiCards = this.buildKpiCards(this.state.kpis);

            this.state.campaigns = data.campaigns || [];

            this.state.campaignStates = data.campaign_states || [];

        } catch (_e) {

            if (!silent) {

                this.notification.add("Impossible de charger le tableau de bord.", {

                    type: "danger",

                });

            }

        } finally {

            this.state.loading = false;

            this.state.silentRefresh = false;

        }

    }



    onDateFromChange(ev) {

        this.state.dateFrom = ev.target.value;

        this.load();

    }



    onDateToChange(ev) {

        this.state.dateTo = ev.target.value;

        this.load();

    }



    setQualification(qualId) {

        this.state.activeQualification = qualId;

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

}



registry.category("actions").add(

    "calls_coaching_dashboard_action",

    CallsCoachingDashboard

);

