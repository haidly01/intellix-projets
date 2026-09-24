/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

const POLL_MS = 5000;

const vicidialLeadSyncService = {
    dependencies: ["action", "notification", "bus_service"],

    start(env, { action, notification, bus_service }) {
        const uid = session.uid;
        if (!uid) {
            return {};
        }

        let lastCallUid = null;
        let pollTimer = null;
        let openedLeadId = null;
        let sessionActive = false;

        const openLead = (leadId, leadName, phone, viewId) => {
            if (!leadId || openedLeadId === leadId) {
                return;
            }
            openedLeadId = leadId;
            notification.add(
                `Appel en cours — ${leadName || "Contact"} (${phone || ""})`,
                {
                    type: "warning",
                    sticky: true,
                    title: "Appels — Appel actif",
                }
            );
            action.doAction({
                type: "ir.actions.act_window",
                res_model: "crm.lead",
                res_id: leadId,
                view_mode: "form",
                views: viewId ? [[viewId, "form"]] : [[false, "form"]],
                target: "current",
            });
        };

        const handlePayload = (payload) => {
            if (!payload || !payload.event) {
                return;
            }
            if (payload.event === "lead_open" && payload.lead_id) {
                if (payload.call_uid && payload.call_uid === lastCallUid) {
                    return;
                }
                lastCallUid = payload.call_uid || null;
                openLead(
                    payload.lead_id,
                    payload.lead_name,
                    payload.phone,
                    payload.view_id
                );
            }
            if (payload.event === "call_ended") {
                lastCallUid = null;
                openedLeadId = null;
                notification.add("Appel terminé — retour file qualification…", {
                    type: "info",
                    title: "Appels",
                });
                setTimeout(() => {
                    action.doAction("doorway_vicidial_campaigns.action_vicidial_qualification_hub");
                }, 2500);
            }
        };

        const poll = async () => {
            if (!sessionActive) {
                return;
            }
            try {
                const response = await fetch("/doorway/vicidial/qualification/poll", {
                    method: "GET",
                    credentials: "same-origin",
                });
                if (response.ok) {
                    handlePayload(await response.json());
                }
            } catch (_e) {
                // ignore transient network errors
            }
        };

        bus_service.subscribe("doorway/vicidial/lead_open", (payload) => {
            handlePayload({ event: "lead_open", ...payload });
        });
        bus_service.subscribe("doorway/vicidial/call_ended", (payload) => {
            handlePayload({ event: "call_ended", ...payload });
        });

        pollTimer = setInterval(poll, POLL_MS);

        return {
            setSessionActive(active) {
                sessionActive = !!active;
                if (sessionActive) {
                    poll();
                }
            },
            stop() {
                if (pollTimer) {
                    clearInterval(pollTimer);
                }
            },
        };
    },
};

registry.category("services").add("doorway_vicidial_lead_sync", vicidialLeadSyncService);
