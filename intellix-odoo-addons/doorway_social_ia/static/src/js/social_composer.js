/** @odoo-module **/

import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MAX_IMAGE_BYTES = 30 * 1024 * 1024; // 30 Mo
const MAX_VIDEO_BYTES = 300 * 1024 * 1024; // 300 Mo
const ACCEPTED = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/quicktime",
    "video/webm",
];

export class DoorwaySocialComposer extends Component {
    static template = "doorway_social_ia.Composer";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.fileInput = useRef("fileInput");
        this.state = useState({
            loading: true,
            saving: false,
            teams: [],
            accounts: [],
            bestTimes: {},
            igMaxMedia: 10,
            creditBalance: 0,
            publishCost: 1,
            pipelineId: null,
            selectedAccountIds: [],
            threadsEnabled: false,
            caption: "",
            hashtags: "",
            privacy: "public",
            postFormat: "publication",
            media: [],
            scheduleEnabled: false,
            scheduledDate: "",
            activePreview: "facebook",
            warning: "",
        });
        onMounted(() => this._load());
    }

    async _load() {
        this.state.loading = true;
        try {
            const ctx = await this.orm.call(
                "doorway.social.post",
                "get_composer_context",
                []
            );
            this.state.teams = ctx.teams || [];
            this.state.accounts = ctx.accounts || [];
            this.state.bestTimes = ctx.best_times || {};
            this.state.igMaxMedia = ctx.ig_max_media || 10;
            this.state.creditBalance = ctx.credit_balance || 0;
            this.state.publishCost = ctx.publish_cost || 1;
            if (this.state.teams.length) {
                this.state.pipelineId = this.state.teams[0].id;
            }
            // Pré-sélection : tous les comptes connectés
            this.state.selectedAccountIds = this.state.accounts
                .filter((a) => a.connection_state === "connected")
                .map((a) => a.id);
        } catch (e) {
            this.notification.add(
                "Impossible de charger le composer : " + (e.message || e),
                { type: "danger" }
            );
        }
        this.state.loading = false;
    }

    // ------------------------------------------------------------------
    // Médias
    // ------------------------------------------------------------------
    triggerUpload() {
        if (this.fileInput.el) {
            this.fileInput.el.click();
        }
    }

    onFileChange(ev) {
        const files = Array.from(ev.target.files || []);
        files.forEach((file) => this._addFile(file));
        ev.target.value = "";
    }

    _addFile(file) {
        if (ACCEPTED.length && !ACCEPTED.includes(file.type)) {
            this.notification.add(
                `Format non supporté : ${file.name} (${file.type || "?"})`,
                { type: "warning" }
            );
            return;
        }
        const isVideo = (file.type || "").startsWith("video/");
        const limit = isVideo ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES;
        if (file.size > limit) {
            this.notification.add(
                `${file.name} dépasse la taille maximale (${Math.round(
                    limit / 1024 / 1024
                )} Mo).`,
                { type: "warning" }
            );
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const dataUrl = reader.result;
            const base64 = String(dataUrl).split(",")[1] || "";
            this.state.media.push({
                name: file.name,
                mimetype: file.type,
                isVideo,
                dataUrl,
                datas: base64,
            });
        };
        reader.readAsDataURL(file);
    }

    removeMedia(index) {
        this.state.media.splice(index, 1);
    }

    get images() {
        return this.state.media.filter((m) => !m.isVideo);
    }

    get videos() {
        return this.state.media.filter((m) => m.isVideo);
    }

    // ------------------------------------------------------------------
    // Comptes / réseaux
    // ------------------------------------------------------------------
    toggleAccount(id) {
        const idx = this.state.selectedAccountIds.indexOf(id);
        if (idx >= 0) {
            this.state.selectedAccountIds.splice(idx, 1);
        } else {
            this.state.selectedAccountIds.push(id);
        }
    }

    isAccountSelected(id) {
        return this.state.selectedAccountIds.includes(id);
    }

    get facebookAccounts() {
        return this.state.accounts.filter((a) => a.platform === "facebook");
    }

    get tiktokAccounts() {
        return this.state.accounts.filter((a) => a.platform === "tiktok");
    }

    accountIcon(platform) {
        if (platform === "instagram") {
            return "fa-instagram";
        }
        if (platform === "tiktok") {
            return "fa-play-circle";
        }
        return "fa-facebook";
    }

    accountById(id) {
        return this.state.accounts.find((a) => a.id === id);
    }

    // ------------------------------------------------------------------
    // Aperçu
    // ------------------------------------------------------------------
    setPreview(tab) {
        this.state.activePreview = tab;
    }

    get brandName() {
        const selected = this.state.selectedAccountIds
            .map((id) => this.accountById(id))
            .filter(Boolean);
        const fb = selected.find((a) => a.platform === "facebook");
        if (fb) {
            return fb.name;
        }
        const team = this.state.teams.find((t) => t.id === this.state.pipelineId);
        return team ? team.name : "Votre page";
    }

    get igHandle() {
        const ig = this.state.selectedAccountIds
            .map((id) => this.accountById(id))
            .find((a) => a && a.platform === "instagram");
        if (ig) {
            return ig.name.startsWith("@") ? ig.name : "@" + ig.name;
        }
        return "@votre_compte";
    }

    get previewCaption() {
        const parts = [this.state.caption];
        if (this.state.hashtags) {
            parts.push(this.state.hashtags);
        }
        return parts.filter(Boolean).join("\n\n");
    }

    get hasConnectedSelection() {
        return this.state.selectedAccountIds
            .map((id) => this.accountById(id))
            .some((a) => a && a.connection_state === "connected");
    }

    // ------------------------------------------------------------------
    // Programmation
    // ------------------------------------------------------------------
    toggleSchedule() {
        this.state.scheduleEnabled = !this.state.scheduleEnabled;
    }

    bestTimeSuggestions() {
        const platform = this.state.activePreview === "instagram"
            ? "instagram"
            : "facebook";
        const hour = this.state.bestTimes[platform] || 10;
        const out = [];
        for (let d = 0; d < 3; d++) {
            const dt = new Date();
            dt.setDate(dt.getDate() + d);
            dt.setHours(hour, 0, 0, 0);
            out.push({
                label:
                    (d === 0 ? "Aujourd'hui" : d === 1 ? "Demain" : dt.toLocaleDateString("fr-CA", { weekday: "short", day: "2-digit", month: "2-digit" })) +
                    " " +
                    dt.toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" }),
                value: this._toOdooDatetime(dt),
            });
        }
        return out;
    }

    pickBestTime(value) {
        this.state.scheduleEnabled = true;
        this.state.scheduledDate = value;
    }

    _toOdooDatetime(dt) {
        const pad = (n) => String(n).padStart(2, "0");
        return (
            `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ` +
            `${pad(dt.getHours())}:${pad(dt.getMinutes())}:00`
        );
    }

    onScheduleInput(ev) {
        // input type=datetime-local => "YYYY-MM-DDTHH:MM"
        const v = ev.target.value;
        if (!v) {
            this.state.scheduledDate = "";
            return;
        }
        this.state.scheduledDate = v.replace("T", " ") + ":00";
    }

    // ------------------------------------------------------------------
    // Enregistrement / publication
    // ------------------------------------------------------------------
    async _persist(publishNow) {
        if (!this.state.selectedAccountIds.length) {
            this.notification.add(
                "Sélectionnez au moins un compte Facebook, Instagram ou TikTok.",
                { type: "warning" }
            );
            return;
        }
        if (!this.state.caption && !this.state.media.length) {
            this.notification.add("Ajoutez du texte ou un média.", {
                type: "warning",
            });
            return;
        }
        // Validation IG : 10 images max
        const igSelected = this.state.selectedAccountIds
            .map((id) => this.accountById(id))
            .some((a) => a && a.platform === "instagram");
        if (igSelected && this.images.length > this.state.igMaxMedia) {
            this.notification.add(
                `Instagram : ${this.state.igMaxMedia} images maximum.`,
                { type: "danger" }
            );
            return;
        }
        const ttSelected = this.state.selectedAccountIds
            .map((id) => this.accountById(id))
            .some((a) => a && a.platform === "tiktok");
        if (ttSelected && !this.videos.length) {
            this.notification.add(
                "TikTok exige une vidéo (mp4 / mov / webm) avant publication.",
                { type: "danger" }
            );
            return;
        }

        this.state.saving = true;
        this.state.warning = "";
        try {
            // Un post par plateforme ciblée (FB / IG) avec ses comptes.
            const byPlatform = {};
            this.state.selectedAccountIds.forEach((id) => {
                const acc = this.accountById(id);
                if (!acc) {
                    return;
                }
                (byPlatform[acc.platform] = byPlatform[acc.platform] || []).push(id);
            });

            const mediaPayload = this.state.media.map((m) => ({
                name: m.name,
                mimetype: m.mimetype,
                datas: m.datas,
            }));
            const scheduled =
                this.state.scheduleEnabled && this.state.scheduledDate
                    ? this.state.scheduledDate
                    : false;

            const warnings = [];
            let lastId = null;
            let paywall = null;
            for (const [platform, ids] of Object.entries(byPlatform)) {
                const res = await this.orm.call(
                    "doorway.social.post",
                    "create_from_composer",
                    [
                        {
                            pipeline_id: this.state.pipelineId,
                            platform,
                            post_format: this.state.postFormat,
                            caption: this.state.caption,
                            hashtags: this.state.hashtags,
                            privacy: this.state.privacy,
                            account_ids: ids,
                            scheduled_date: scheduled,
                            publish_now: publishNow,
                            media: mediaPayload,
                        },
                    ]
                );
                lastId = res.id;
                if (res.warning) {
                    warnings.push(res.warning);
                }
                if (res.paywall) {
                    paywall = res.paywall;
                }
            }

            // Solde insuffisant → ouvrir le paywall (le(s) post(s) restent en brouillon).
            if (paywall) {
                this.state.saving = false;
                if (warnings.length) {
                    this.notification.add(warnings.join(" "), { type: "warning" });
                }
                await this.action.doAction(paywall);
                return;
            }

            if (this.state.threadsEnabled) {
                warnings.push(
                    "Threads : aperçu uniquement — la publication via l'API Threads n'est pas encore connectée."
                );
            }

            if (warnings.length) {
                this.state.warning = warnings.join(" ");
                this.notification.add(warnings.join(" "), { type: "warning" });
            } else {
                this.notification.add(
                    publishNow
                        ? "Publication envoyée."
                        : scheduled
                        ? "Publication programmée."
                        : "Brouillon enregistré.",
                    { type: "success" }
                );
            }
            this._reset();
        } catch (e) {
            this.notification.add("Erreur : " + (e.message || e), {
                type: "danger",
            });
        }
        this.state.saving = false;
    }

    publish() {
        this._persist(true);
    }

    schedule() {
        this._persist(false);
    }

    _reset() {
        this.state.caption = "";
        this.state.hashtags = "";
        this.state.media = [];
        this.state.scheduleEnabled = false;
        this.state.scheduledDate = "";
    }

    openCalendar() {
        this.action.doAction("doorway_social_ia.action_social_calendar");
    }
}

registry.category("actions").add("social_composer_action", DoorwaySocialComposer);
