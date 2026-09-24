/** @odoo-module **/

import { Component, markup, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DoorwayCrmWebmail extends Component {
    static template = "doorway_crm.WebmailView";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        const params = this.props.action?.params || {};
        const isMobile = this._detectMobile();
        this.state = useState({
            mailboxes: [],
            selectedMailboxId: params.mailbox_id || null,
            folder: "inbox",
            searchQuery: "",
            messages: [],
            total: 0,
            selectedMessage: null,
            selectedBody: null,
            mode: "read",
            compose: {
                to: "",
                cc: "",
                bcc: "",
                subject: "",
                body: "",
                replyMessageId: null,
                attachments: [],
            },
            showCcBcc: false,
            loading: true,
            loadingMessages: false,
            loadingMessage: false,
            sending: false,
            fetching: false,
            statusMessage: "",
            isMobile,
            mobilePane: isMobile ? "list" : "list",
        });

        this._mobileMq = window.matchMedia("(max-width: 900px)");
        this._touchMq = window.matchMedia("(hover: none) and (pointer: coarse)");
        this._onMobileChange = () => this._syncMobileLayout();

        onMounted(() => {
            this._syncMobileLayout();
            this._mobileMq.addEventListener("change", this._onMobileChange);
            this._touchMq.addEventListener("change", this._onMobileChange);
            this._init();
        });
        onWillUnmount(() => {
            this._mobileMq.removeEventListener("change", this._onMobileChange);
            this._touchMq.removeEventListener("change", this._onMobileChange);
        });
    }

    _detectMobile() {
        return (
            window.matchMedia("(max-width: 900px)").matches ||
            window.matchMedia("(hover: none) and (pointer: coarse)").matches
        );
    }

    _syncMobileLayout() {
        const mobile = this._detectMobile();
        const wasMobile = this.state.isMobile;
        this.state.isMobile = mobile;
        if (mobile && !wasMobile) {
            this.state.mobilePane = this.state.selectedMailboxId ? "list" : "nav";
        } else if (!mobile) {
            this.state.mobilePane = "list";
        }
    }

    _goMobilePane(pane) {
        if (this.state.isMobile) {
            this.state.mobilePane = pane;
            if (pane === "list" && this.state.selectedMailboxId) {
                this._loadMessages();
            }
        }
    }

    showMessagesTab() {
        if (!this.state.selectedMailboxId) {
            this._goMobilePane("nav");
            return;
        }
        this.state.mode = "read";
        this._goMobilePane("list");
    }

    mobileBack() {
        if (!this.state.isMobile) {
            return;
        }
        if (this.state.mobilePane === "read" || this.state.mode === "compose") {
            this.state.mode = "read";
            this.state.mobilePane = "list";
        } else if (this.state.mobilePane === "list") {
            this.state.mobilePane = "nav";
        }
    }

    async _init() {
        this.state.loading = true;
        try {
            this.state.mailboxes = await this.orm.call(
                "doorway.crm.mailbox",
                "get_webmail_mailboxes",
                []
            );
            if (!this.state.selectedMailboxId && this.state.mailboxes.length) {
                this.state.selectedMailboxId = this._pickDefaultMailboxId();
            }
            if (this.state.selectedMailboxId) {
                await this._loadMessages();
                if (this.state.isMobile) {
                    this.state.mobilePane = "list";
                }
            }
        } catch (err) {
            this._notifyError(err);
        } finally {
            this.state.loading = false;
        }
    }

    async _loadMessages() {
        if (!this.state.selectedMailboxId) {
            return;
        }
        this.state.loadingMessages = true;
        try {
            const result = await this.orm.call(
                "doorway.crm.mailbox",
                "get_webmail_messages",
                [],
                {
                    mailbox_id: this.state.selectedMailboxId,
                    folder: this.state.folder,
                    search: this.state.searchQuery,
                    limit: 100,
                    offset: 0,
                }
            );
            this.state.messages = result.messages || [];
            this.state.total = result.total || 0;
            if (
                this.state.selectedMessage &&
                !this.state.messages.find(
                    (m) => m.id === this.state.selectedMessage.id
                )
            ) {
                this.state.selectedMessage = null;
                this.state.selectedBody = null;
                this.state.mode = "read";
            }
        } catch (err) {
            this._notifyError(err);
        } finally {
            this.state.loadingMessages = false;
        }
    }

    async selectMailbox(mailboxId) {
        if (this.state.selectedMailboxId === mailboxId) {
            return;
        }
        this.state.selectedMailboxId = mailboxId;
        this.state.selectedMessage = null;
        this.state.selectedBody = null;
        this.state.mode = "read";
        await this._loadMessages();
        this._goMobilePane("list");
    }

    async setFolder(folder) {
        if (this.state.folder === folder) {
            return;
        }
        this.state.folder = folder;
        this.state.selectedMessage = null;
        this.state.selectedBody = null;
        this.state.mode = "read";
        await this._loadMessages();
        this._goMobilePane("list");
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        this._loadMessages();
    }

    async selectMessage(msg) {
        this.state.mode = "read";
        this.state.loadingMessage = true;
        try {
            const detail = await this.orm.call(
                "doorway.crm.mailbox",
                "get_webmail_message",
                [],
                { message_id: msg.id, mailbox_id: this.state.selectedMailboxId }
            );
            this.state.selectedMessage = detail;
            this.state.selectedBody = markup(detail.body_html || "");
        } catch (err) {
            this._notifyError(err);
        } finally {
            this.state.loadingMessage = false;
        }
        this._goMobilePane("read");
    }

    _pickDefaultMailboxId() {
        const boxes = this.state.mailboxes || [];
        const mine = boxes.filter((m) => m.is_owner);
        const picked =
            mine.find((m) => m.is_default) ||
            mine.find((m) => m.message_count > 0) ||
            mine[0] ||
            boxes.find((m) => m.is_default) ||
            boxes[0];
        return picked ? picked.id : null;
    }

    _ensureMailboxSelected() {
        if (this.state.selectedMailboxId || !this.state.mailboxes.length) {
            return;
        }
        this.state.selectedMailboxId = this._pickDefaultMailboxId();
    }

    openCompose() {
        this._ensureMailboxSelected();
        this.state.mode = "compose";
        this._goMobilePane("compose");
        this.state.compose = {
            to: "",
            cc: "",
            bcc: "",
            subject: "",
            body: "",
            replyMessageId: null,
            attachments: [],
        };
        this.state.showCcBcc = false;
    }

    openReply() {
        if (!this.state.selectedMessage) {
            this.notification.add("Ouvrez d’abord un message pour y répondre.", {
                type: "warning",
            });
            return;
        }
        this._ensureMailboxSelected();
        const msg = this.state.selectedMessage;
        const subject = msg.subject || "";
        const reSubject = subject.toLowerCase().startsWith("re:")
            ? subject
            : `Re: ${subject}`;
        this.state.mode = "compose";
        this.state.compose = {
            to: this._extractEmail(msg.email_from || msg.reply_to || ""),
            cc: "",
            bcc: "",
            subject: reSubject,
            body: "\n\n---\n" + (msg.snippet || ""),
            replyMessageId: msg.id,
            attachments: [],
        };
        this.state.showCcBcc = false;
        this._goMobilePane("compose");
    }

    openForward() {
        if (!this.state.selectedMessage) {
            this.notification.add("Ouvrez d’abord un message à transférer.", {
                type: "warning",
            });
            return;
        }
        this._ensureMailboxSelected();
        const msg = this.state.selectedMessage;
        const subject = msg.subject || "";
        const fwSubject = subject.toLowerCase().startsWith("fwd:")
            ? subject
            : `Fwd: ${subject}`;
        this.state.mode = "compose";
        this.state.compose = {
            to: "",
            cc: "",
            bcc: "",
            subject: fwSubject,
            body: "\n\n---------- Message transféré ----------\n" + (msg.snippet || ""),
            replyMessageId: null,
            attachments: [],
        };
        this.state.showCcBcc = false;
        this._goMobilePane("compose");
    }

    cancelCompose() {
        this.state.mode = "read";
        if (this.state.isMobile) {
            this.state.mobilePane = this.state.selectedMessage ? "read" : "list";
        }
    }

    toggleCcBcc() {
        this.state.showCcBcc = !this.state.showCcBcc;
    }

    onComposeInput(field, ev) {
        this.state.compose[field] = ev.target.value;
    }

    formatFileSize(bytes) {
        if (bytes >= 1048576) {
            return (bytes / 1048576).toFixed(1).replace(".", ",") + " Mo";
        }
        return Math.max(1, Math.round(bytes / 1024)) + " Ko";
    }

    async onAttachFiles(ev) {
        const MAX_FILES = 10;
        const MAX_BYTES = 20 * 1024 * 1024;
        const files = Array.from(ev.target.files || []);
        ev.target.value = "";
        for (const file of files) {
            const list = this.state.compose.attachments;
            const total = list.reduce((sum, a) => sum + a.size, 0);
            if (list.length >= MAX_FILES) {
                this.notification.add("Maximum 10 pièces jointes par message.", { type: "warning" });
                break;
            }
            if (total + file.size > MAX_BYTES) {
                this.notification.add(
                    `« ${file.name} » n’a pas été ajouté : le total dépasserait 20 Mo.`,
                    { type: "warning" }
                );
                continue;
            }
            try {
                const data = await this._readFileBase64(file);
                list.push({
                    name: file.name,
                    size: file.size,
                    mimetype: file.type || "application/octet-stream",
                    data,
                });
            } catch {
                this.notification.add(`Impossible de lire « ${file.name} ».`, { type: "danger" });
            }
        }
    }

    _readFileBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    removeAttachment(index) {
        this.state.compose.attachments.splice(index, 1);
    }

    async sendMail() {
        if (this.state.sending) {
            return;
        }
        this.state.sending = true;
        this.state.statusMessage = "";
        try {
            await this.orm.call(
                "doorway.crm.mailbox",
                "action_send_webmail",
                [],
                {
                    mailbox_id: this.state.selectedMailboxId,
                    to_addrs: this.state.compose.to,
                    subject: this.state.compose.subject,
                    body_html: this.state.compose.body,
                    cc_addrs: this.state.compose.cc,
                    bcc_addrs: this.state.compose.bcc,
                    reply_message_id: this.state.compose.replyMessageId,
                    attachments: this.state.compose.attachments.map((a) => ({
                        name: a.name,
                        mimetype: a.mimetype,
                        data: a.data,
                    })),
                }
            );
            this.notification.add("E-mail envoyé.", { type: "success" });
            this.state.mode = "read";
            this.state.folder = "sent";
            await this._loadMessages();
        } catch (err) {
            this._notifyError(err);
        } finally {
            this.state.sending = false;
        }
    }

    async fetchEmails() {
        if (!this.state.selectedMailboxId || this.state.fetching) {
            return;
        }
        this.state.fetching = true;
        this.state.statusMessage = "";
        try {
            await this.orm.call(
                "doorway.crm.mailbox",
                "action_fetch_now",
                [[this.state.selectedMailboxId]]
            );
            this.state.statusMessage = "Synchronisation terminée.";
            await this._loadMessages();
        } catch (err) {
            this._notifyError(err);
        } finally {
            this.state.fetching = false;
        }
    }

    openMailboxSettings() {
        this.action.doAction("doorway_crm.action_doorway_crm_mailbox_list");
    }

    openAddMailbox() {
        this.action.doAction("doorway_crm.action_doorway_crm_mailbox_setup");
    }

    _extractEmail(addr) {
        if (!addr) {
            return "";
        }
        const match = addr.match(/<([^>]+)>/);
        return match ? match[1] : addr;
    }

    _notifyError(err) {
        const msg =
            err?.data?.message ||
            err?.message ||
            "Une erreur est survenue.";
        this.notification.add(msg, { type: "danger" });
    }

    formatDate(iso) {
        if (!iso) {
            return "";
        }
        try {
            return new Date(iso).toLocaleString("fr-CA", {
                year: "numeric",
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch {
            return iso;
        }
    }

    formatShortDate(iso) {
        if (!iso) {
            return "";
        }
        try {
            const d = new Date(iso);
            const now = new Date();
            if (d.toDateString() === now.toDateString()) {
                return d.toLocaleString("fr-CA", {
                    hour: "2-digit",
                    minute: "2-digit",
                });
            }
            return d.toLocaleString("fr-CA", {
                month: "short",
                day: "numeric",
            });
        } catch {
            return iso;
        }
    }

    isSelectedMessage(msg) {
        return (
            this.state.selectedMessage &&
            this.state.selectedMessage.id === msg.id
        );
    }

    get selectedMailbox() {
        return this.state.mailboxes.find(
            (m) => m.id === this.state.selectedMailboxId
        );
    }

    get showNavPane() {
        return !this.state.isMobile || this.state.mobilePane === "nav";
    }

    get showListPane() {
        return !this.state.isMobile || this.state.mobilePane === "list";
    }

    get showContentPane() {
        return (
            !this.state.isMobile ||
            this.state.mobilePane === "read" ||
            this.state.mobilePane === "compose"
        );
    }

    get folderLabel() {
        const labels = {
            inbox: "Boîte de réception",
            sent: "Envoyés",
            junk: "Spam",
            trash: "Corbeille",
            all: "Tous les messages",
        };
        return labels[this.state.folder] || this.state.folder;
    }

    get mobileBarTitle() {
        if (this.state.mode === "compose") {
            return "Nouveau message";
        }
        if (this.state.mobilePane === "read" && this.state.selectedMessage) {
            return this.state.selectedMessage.subject || "Message";
        }
        if (this.state.mobilePane === "list") {
            const mb = this.selectedMailbox;
            return mb ? `${this.folderLabel} — ${mb.name}` : this.folderLabel;
        }
        return "Boîte mail";
    }
}

registry.category("actions").add("doorway_crm_webmail_action", DoorwayCrmWebmail);
