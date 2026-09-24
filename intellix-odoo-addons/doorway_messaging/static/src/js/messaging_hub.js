/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const SIDEBAR_ITEMS = [
    { id: "hub", label: "Accueil", icon: "fa-home", action: null },
    { id: "assign", label: "Multi-contacts", icon: "fa-users", action: "doorway_messaging.action_assign_campaign_wizard" },
    { id: "campaign", label: "Campagnes", icon: "fa-bullhorn", action: "doorway_messaging.action_message_campaign" },
    { id: "compose", label: "Nouveau", icon: "fa-pencil", action: "doorway_messaging.action_open_compose_wizard" },
    { id: "history", label: "Historique", icon: "fa-history", action: "doorway_messaging.action_message_log" },
    { id: "templates", label: "Templates", icon: "fa-file-text-o", action: "doorway_messaging.action_message_template" },
    { id: "channels", label: "Canaux", icon: "fa-plug", action: "doorway_messaging.action_channel_config" },
];

const CAROUSEL_SLIDES = [
    [
        {
            key: "whatsapp",
            icon: "fa-users",
            title: "Campagne multi-contacts",
            subtitle: "Assignez plusieurs contacts à une campagne WhatsApp et SMS avec vos templates Twilio approuvés.",
            primaryLabel: "WhatsApp + SMS",
            primaryAction: "doorway_messaging.action_assign_campaign_wizard",
            primaryContext: { default_canal_whatsapp: true, default_canal_sms: true },
            secondaryLabel: "WhatsApp rapide",
            secondaryAction: "doorway_messaging.action_whatsapp_send_wizard",
        },
        {
            key: "email",
            icon: "fa-paper-plane",
            title: "Diffusion email",
            subtitle: "Relancez vos leads par email avec templates et suivi.",
            primaryLabel: "Campagnes",
            primaryAction: "doorway_messaging.action_message_campaign",
            secondaryLabel: "Email",
            secondaryAction: "doorway_messaging.action_open_compose_wizard",
            secondaryContext: { default_canal_email: true },
        },
    ],
    [
        {
            key: "bulk",
            icon: "fa-users",
            title: "Sélection leads",
            subtitle: "Ciblez vos prospects CRM pour une campagne ciblée.",
            primaryLabel: "Sélectionner",
            primaryAction: "doorway_messaging.action_bulk_select_wizard",
            secondaryLabel: "Historique",
            secondaryAction: "doorway_messaging.action_message_log",
        },
        {
            key: "social",
            icon: "fa-comments",
            title: "Messages sociaux",
            subtitle: "Inbox unifiée WhatsApp, Messenger, LinkedIn et GMB.",
            primaryLabel: "Inbox",
            primaryAction: "doorway_social_ia.action_social_inbox_unified",
            secondaryLabel: "Comptes",
            secondaryAction: "doorway_social_ia.action_social_accounts_linkedin_gmb",
        },
    ],
];

export class MessagingHubDashboard extends Component {
    static template = "doorway_messaging.MessagingHub";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            channels: [],
            campaignStats: { total: 0, active: 0, draft: 0 },
            features: { social_inbox: false },
            activeNav: "hub",
            carouselIndex: 0,
        });
        onMounted(() => this.loadData());
    }

    get sidebarItems() {
        const items = [...SIDEBAR_ITEMS];
        if (this.state.features.social_inbox) {
            items.push({
                id: "messages",
                label: "Messages",
                icon: "fa-commenting",
                action: "doorway_social_ia.action_social_inbox_unified",
                bottom: true,
            });
        }
        return items;
    }

    get mainSidebarItems() {
        return this.sidebarItems.filter((i) => !i.bottom);
    }

    get bottomSidebarItems() {
        return this.sidebarItems.filter((i) => i.bottom);
    }

    get currentSlide() {
        return CAROUSEL_SLIDES[this.state.carouselIndex] || CAROUSEL_SLIDES[0];
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("doorway.messaging.hub", "get_hub_data", []);
            this.state.channels = data.channels || [];
            this.state.campaignStats = data.campaign_stats || { total: 0, active: 0, draft: 0 };
            this.state.features = data.features || { social_inbox: false };
        } catch (err) {
            console.error(err);
            this.notification.add("Impossible de charger le Messaging Hub.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async openAction(xmlId, extra = {}) {
        if (!xmlId) {
            return;
        }
        try {
            await this.action.doAction(xmlId, extra);
        } catch (err) {
            console.error(err);
            this.notification.add("Action indisponible.", { type: "warning" });
        }
    }

    onNavClick(item) {
        if (item.id === "hub") {
            this.state.activeNav = "hub";
            return;
        }
        this.state.activeNav = item.id;
        this.openAction(item.action);
    }

    onCarouselDot(index) {
        this.state.carouselIndex = index;
    }

    onCardPrimary(card) {
        this.openAction(card.primaryAction, card.primaryContext ? { additionalContext: card.primaryContext } : {});
    }

    onCardSecondary(card) {
        this.openAction(card.secondaryAction, card.secondaryContext ? { additionalContext: card.secondaryContext } : {});
    }

    async onChannelClick(channel) {
        if (channel.config_id) {
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "doorway.channel.config",
                res_id: channel.config_id,
                views: [[false, "form"]],
                target: "current",
            });
            return;
        }
        await this.openAction("doorway_messaging.action_channel_config", {
            additionalContext: { default_canal: channel.canal },
        });
    }

    async onAddChannel() {
        await this.openAction("doorway_messaging.action_channel_config", {
            additionalContext: { form_view_initial_mode: "edit" },
        });
    }

    async onDisconnectChannel(channel, ev) {
        ev.stopPropagation();
        try {
            await this.orm.call("doorway.messaging.hub", "disconnect_channel", [channel.canal]);
            this.notification.add(`${channel.title} déconnecté.`, { type: "info" });
            await this.loadData();
        } catch (err) {
            console.error(err);
            this.notification.add("Échec de la déconnexion.", { type: "danger" });
        }
    }
}

registry.category("actions").add("messaging_hub_action", MessagingHubDashboard);
