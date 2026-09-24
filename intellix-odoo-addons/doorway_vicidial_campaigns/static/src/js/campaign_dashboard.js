/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const REFRESH_MS = 30000;

const STATE_BADGE = {
    active: "ix-camp-badge--active",
    paused: "ix-camp-badge--paused",
    completed: "ix-camp-badge--done",
    draft: "ix-camp-badge--draft",
    ready: "ix-camp-badge--ready",
};

const STATUS_BADGE = {
    success: "ix-camp-status--success",
    callback: "ix-camp-status--callback",
    voicemail: "ix-camp-status--vm",
    error: "ix-camp-status--error",
    in_progress: "ix-camp-status--progress",
};

class CampaignDashboard extends Component {
    static template = "doorway_vicidial_campaigns.CampaignDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            view: "list",
            loading: true,
            campaigns: [],
            agents: [],
            pipelines: [],
            filters: {
                pipeline: "",
                agent_id: "",
                state: "",
                period: "week",
            },
            summary: null,
            period: null,
            selectedCampaignId: null,
            detail: null,
            detailFilters: {
                operational_status: "",
                ai_score_min: "",
                ai_score_max: "",
                timeline_period: "today",
            },
            page: 1,
            selectedIds: [],
            drawer: null,
            drawerOpen: false,
            bulkLoading: false,
            campaignActionLoading: false,
        });
        this._timer = null;
        this._onVisibilityChange = () => {
            if (document.hidden) {
                this._pausePolling();
            } else {
                this._refreshCurrentView(false);
                this._resumePolling();
            }
        };
        onMounted(() => {
            document.addEventListener("visibilitychange", this._onVisibilityChange);
            this.init();
            this._resumePolling();
        });
        onWillUnmount(() => {
            document.removeEventListener("visibilitychange", this._onVisibilityChange);
            this._pausePolling();
        });
    }

    _resumePolling() {
        if (this._timer || document.hidden) {
            return;
        }
        this._timer = setInterval(() => this._refreshCurrentView(false), REFRESH_MS);
    }

    _pausePolling() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    async _refreshCurrentView(showSpinner = false) {
        if (this.state.view === "detail" && this.state.selectedCampaignId) {
            await this.loadDetail(showSpinner);
        } else {
            await this.loadList(showSpinner);
        }
    }

    async init() {
        const ctx = this.props.action?.context || {};
        await this.loadList();
        if (ctx.default_campaign_id) {
            await this.openCampaign(ctx.default_campaign_id);
        }
    }

    async loadList(showSpinner = true) {
        if (showSpinner) {
            this.state.loading = true;
        }
        try {
            const f = {};
            if (this.state.filters.pipeline) f.pipeline = this.state.filters.pipeline;
            if (this.state.filters.agent_id) f.agent_id = this.state.filters.agent_id;
            if (this.state.filters.state) f.state = this.state.filters.state;
            if (this.state.filters.period) f.period = this.state.filters.period;
            const data = await this.orm.call(
                "doorway.campaign",
                "dashboard_list_campaigns",
                [],
                f
            );
            this.state.campaigns = data.campaigns || [];
            this.state.agents = data.agents || [];
            this.state.pipelines = data.pipelines || [];
            this.state.summary = data.summary || null;
            this.state.period = data.period || null;
        } catch (err) {
            this.notification.add(err.message || "Erreur chargement campagnes.", {
                type: "danger",
            });
        } finally {
            if (showSpinner) {
                this.state.loading = false;
            }
        }
    }

    async openCampaign(id) {
        this.state.selectedCampaignId = id;
        this.state.view = "detail";
        this.state.page = 1;
        this.state.selectedIds = [];
        await this.loadDetail();
    }

    async loadDetail(showSpinner = true) {
        if (!this.state.selectedCampaignId) return;
        if (showSpinner) {
            this.state.loading = true;
        }
        try {
            const f = { ...this.state.detailFilters };
            Object.keys(f).forEach((k) => {
                if (!f[k]) delete f[k];
            });
            const data = await this.orm.call(
                "doorway.campaign",
                "dashboard_detail",
                [[this.state.selectedCampaignId], f, this.state.page, 20]
            );
            this.state.detail = data;
        } catch (err) {
            if (showSpinner) {
                this.notification.add(err.message || "Erreur détail campagne.", {
                    type: "danger",
                });
            }
        } finally {
            if (showSpinner) {
                this.state.loading = false;
            }
        }
    }

    backToList() {
        this.state.view = "list";
        this.state.selectedCampaignId = null;
        this.state.detail = null;
        this.state.drawerOpen = false;
        this.loadList();
    }

    setListFilter(key, value) {
        this.state.filters[key] = value;
        this.loadList();
    }

    setDetailFilter(key, value) {
        this.state.detailFilters[key] = value;
        this.state.page = 1;
        this.loadDetail();
    }

    stateBadge(state) {
        return STATE_BADGE[state] || "ix-camp-badge--draft";
    }

    statusBadge(status) {
        return STATUS_BADGE[status] || "";
    }

    toggleSelect(id, checked) {
        const ids = [...this.state.selectedIds];
        const idx = ids.indexOf(id);
        if (checked && idx < 0) ids.push(id);
        if (!checked && idx >= 0) ids.splice(idx, 1);
        this.state.selectedIds = ids;
    }

    toggleSelectAll(checked) {
        if (!this.state.detail?.contacts) return;
        this.state.selectedIds = checked
            ? this.state.detail.contacts.map((c) => c.id)
            : [];
    }

    isSelected(id) {
        return this.state.selectedIds.includes(id);
    }

    async openDrawer(contactId) {
        try {
            const data = await this.orm.call(
                "doorway.campaign",
                "dashboard_contact_drawer",
                [[this.state.selectedCampaignId], contactId]
            );
            this.state.drawer = data;
            this.state.drawerOpen = true;
        } catch (err) {
            this.notification.add(err.message || "Erreur drawer.", { type: "danger" });
        }
    }

    closeDrawer() {
        this.state.drawerOpen = false;
        this.state.drawer = null;
    }

    async relaunchSelected() {
        if (!this.state.selectedIds.length) return;
        this.state.bulkLoading = true;
        try {
            const res = await this.orm.call(
                "doorway.campaign",
                "dashboard_relaunch",
                [[this.state.selectedCampaignId], this.state.selectedIds, "high"]
            );
            this.notification.add(
                `${res.relaunched} contact(s) relancé(s).`,
                { type: "success" }
            );
            this.state.selectedIds = [];
            await this.loadDetail();
        } catch (err) {
            this.notification.add(err.message || "Relance échouée.", { type: "danger" });
        } finally {
            this.state.bulkLoading = false;
        }
    }

    async exportSelected() {
        if (!this.state.selectedIds.length) return;
        try {
            const res = await this.orm.call(
                "doorway.campaign",
                "dashboard_export_csv",
                [[this.state.selectedCampaignId], this.state.selectedIds]
            );
            const link = document.createElement("a");
            link.href = `data:${res.mime};base64,${res.data}`;
            link.download = res.filename;
            link.click();
        } catch (err) {
            this.notification.add(err.message || "Export échoué.", { type: "danger" });
        }
    }

    async pushCrmSelected() {
        if (!this.state.selectedIds.length) return;
        this.state.bulkLoading = true;
        try {
            const res = await this.orm.call(
                "doorway.campaign",
                "dashboard_push_crm",
                [[this.state.selectedCampaignId], this.state.selectedIds]
            );
            this.notification.add(
                `${res.count} lead(s) CRM créé(s).`,
                { type: "success" }
            );
            await this.loadDetail();
        } catch (err) {
            this.notification.add(err.message || "Push CRM échoué.", { type: "danger" });
        } finally {
            this.state.bulkLoading = false;
        }
    }

    async relaunchOne(contactId) {
        this.state.selectedIds = [contactId];
        await this.relaunchSelected();
    }

    async createCrmFromDrawer() {
        if (!this.state.drawer?.id) return;
        try {
            const res = await this.orm.call(
                "doorway.campaign.contact",
                "dashboard_create_crm_lead",
                [[this.state.drawer.id]]
            );
            if (res.created) {
                this.notification.add("Lead Odoo créé.", { type: "success" });
            }
            await this.openDrawer(this.state.drawer.id);
            await this.loadDetail();
        } catch (err) {
            this.notification.add(err.message || "Création lead échouée.", { type: "danger" });
        }
    }

    async changePage(delta) {
        const pages = this.state.detail?.pagination?.pages || 1;
        const next = this.state.page + delta;
        if (next < 1 || next > pages) return;
        this.state.page = next;
        await this.loadDetail();
    }

    timelineMax() {
        const rows = this.state.detail?.timeline || [];
        return Math.max(1, ...rows.map((r) => r.count));
    }

    barHeight(count) {
        const max = this.timelineMax();
        return Math.round((count / max) * 100);
    }

    newCampaign() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "doorway.campaign",
            views: [[false, "form"]],
            target: "current",
        });
    }

    async campaignStart() {
        if (!this.state.selectedCampaignId) {
            return;
        }
        this.state.campaignActionLoading = true;
        try {
            await this.orm.call("doorway.campaign", "action_start", [
                [this.state.selectedCampaignId],
            ]);
            this.notification.add("Campagne démarrée.", { type: "success" });
            await this.loadDetail();
            await this.loadList();
        } catch (err) {
            this.notification.add(err.message || "Démarrage échoué.", {
                type: "danger",
            });
        } finally {
            this.state.campaignActionLoading = false;
        }
    }

    async campaignPause() {
        if (!this.state.selectedCampaignId) {
            return;
        }
        this.state.campaignActionLoading = true;
        try {
            await this.orm.call("doorway.campaign", "action_pause", [
                [this.state.selectedCampaignId],
            ]);
            this.notification.add("Campagne en pause.", { type: "success" });
            await this.loadDetail();
            await this.loadList();
        } catch (err) {
            this.notification.add(err.message || "Pause échouée.", {
                type: "danger",
            });
        } finally {
            this.state.campaignActionLoading = false;
        }
    }

    async campaignImportContacts() {
        if (!this.state.selectedCampaignId) {
            return;
        }
        try {
            const act = await this.orm.call(
                "doorway.campaign",
                "action_open_import_wizard",
                [[this.state.selectedCampaignId]]
            );
            if (act) {
                this.action.doAction(act);
            }
        } catch (err) {
            this.notification.add(err.message || "Import impossible.", {
                type: "danger",
            });
        }
    }

    async campaignCleanupList() {
        if (!this.state.selectedCampaignId) {
            return;
        }
        const ok = window.confirm(
            "Supprimer les numéros invalides et doublons, puis recharger le hopper VICIdial ?"
        );
        if (!ok) {
            return;
        }
        this.state.campaignActionLoading = true;
        try {
            const act = await this.orm.call(
                "doorway.campaign",
                "action_cleanup_list",
                [[this.state.selectedCampaignId]]
            );
            if (act?.params?.message) {
                this.notification.add(act.params.message, {
                    type: act.params.type || "success",
                });
            }
            await this.loadDetail();
            await this.loadList();
        } catch (err) {
            this.notification.add(err.message || "Nettoyage impossible.", {
                type: "danger",
            });
        } finally {
            this.state.campaignActionLoading = false;
        }
    }
}

registry.category("actions").add("campaign_dashboard_action", CampaignDashboard);
