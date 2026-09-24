/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const PLATFORM_ICON = {
    whatsapp: "fa-whatsapp",
    messenger: "fa-facebook",
    telegram: "fa-telegram",
    instagram: "fa-instagram",
    linkedin: "fa-linkedin",
    gmb: "fa-google",
};

export class DoorwaySocialInboxView extends Component {
    static template = "doorway_social_ia.InboxView";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            conversations: [],
            selectedConv: null,
            messages: [],
            comments: [],
            activeTab: "messages",
            filterPlatform: "all",
            filterAccount: "all",
            filterStatus: "all",
            searchQuery: "",
            replyText: "",
            aiSuggestion: null,
            loadingAi: false,
            loading: true,
            syncing: false,
            syncMessage: "",
            accounts: [],
            commentReplies: {},
            commentAiLoading: {},
        });
        onMounted(() => this._loadAll());
    }

    async _loadAll() {
        this.state.loading = true;
        await Promise.all([this._loadConversations(), this._loadAccounts()]);
        this.state.loading = false;
    }

    async syncFromMeta() {
        this.state.syncing = true;
        this.state.syncMessage = "";
        try {
            const stats = await this.orm.call(
                "doorway.social.inbox",
                "action_sync_all_social",
                []
            );
            const parts = [];
            if (stats.messages) {
                parts.push(`${stats.messages} message(s)`);
            }
            if (stats.comments) {
                parts.push(`${stats.comments} commentaire(s)`);
            }
            if (stats.reviews) {
                parts.push(`${stats.reviews} avis GMB`);
            }
            if (stats.errors && stats.errors.length) {
                parts.push(`${stats.errors.length} avertissement(s)`);
            }
            this.state.syncMessage = parts.length
                ? `Sync : ${parts.join(", ")}`
                : "Sync terminée";
            await this._loadAll();
            if (this.state.selectedConv) {
                const conv = this.state.conversations.find(
                    (c) => c.id === this.state.selectedConv.id
                );
                if (conv) {
                    await this.selectConversation(conv);
                }
            }
        } catch (err) {
            this.state.syncMessage = "Erreur de synchronisation";
            console.error(err);
        } finally {
            this.state.syncing = false;
        }
    }

    _filtersPayload() {
        return {
            platform: this.state.filterPlatform,
            account: this.state.filterAccount,
            status: this.state.filterStatus,
            search: this.state.searchQuery,
        };
    }

    async _loadConversations() {
        this.state.conversations = await this.orm.call(
            "doorway.social.inbox",
            "get_inbox_list",
            [this._filtersPayload()]
        );
    }

    async _loadAccounts() {
        this.state.accounts = await this.orm.call(
            "doorway.social.inbox",
            "get_inbox_accounts",
            []
        );
    }

    async selectConversation(conv) {
        const data = await this.orm.call(
            "doorway.social.inbox",
            "get_inbox_thread",
            [conv.id]
        );
        this.state.selectedConv = data.conversation;
        this.state.messages = data.messages || [];
        this.state.comments = data.comments || [];
        this.state.activeTab = "messages";
        this.state.aiSuggestion = null;
        this.state.replyText = "";
        const idx = this.state.conversations.findIndex((c) => c.id === conv.id);
        if (idx >= 0) {
            this.state.conversations[idx] = data.conversation;
        }
    }

    async sendReply() {
        if (!this.state.replyText.trim() || !this.state.selectedConv) {
            return;
        }
        const text = this.state.replyText.trim();
        await this.orm.call(
            "doorway.social.inbox",
            "action_send_message",
            [[this.state.selectedConv.id]],
            { text }
        );
        this.state.messages.push({
            direction: "outbound",
            content: text,
            create_date: new Date().toISOString(),
        });
        this.state.selectedConv.last_message = text;
        this.state.selectedConv.state = "replied";
        this.state.replyText = "";
        this.state.aiSuggestion = null;
        await this._loadConversations();
    }

    async getAiSuggestion() {
        if (!this.state.selectedConv) {
            return;
        }
        this.state.loadingAi = true;
        const suggestion = await this.orm.call(
            "doorway.social.inbox",
            "action_ai_reply_suggestion",
            [[this.state.selectedConv.id]]
        );
        this.state.aiSuggestion = suggestion || "";
        this.state.loadingAi = false;
    }

    applyAiSuggestion() {
        if (this.state.aiSuggestion) {
            this.state.replyText = this.state.aiSuggestion;
            this.state.aiSuggestion = null;
        }
    }

    async replyToComment(commentId) {
        const replyText = (this.state.commentReplies[commentId] || "").trim();
        if (!replyText) {
            return;
        }
        await this.orm.call(
            "doorway.social.comment",
            "action_reply",
            [[commentId]],
            { reply_text: replyText }
        );
        const cmt = this.state.comments.find((c) => c.id === commentId);
        if (cmt) {
            cmt.is_replied = true;
            cmt.reply_content = replyText;
        }
        this.state.commentReplies[commentId] = "";
    }

    async getAiCommentReply(commentId) {
        this.state.commentAiLoading[commentId] = true;
        const suggestion = await this.orm.call(
            "doorway.social.comment",
            "action_ai_reply",
            [[commentId]]
        );
        this.state.commentReplies[commentId] = suggestion || "";
        this.state.commentAiLoading[commentId] = false;
    }

    async createLead() {
        if (!this.state.selectedConv) {
            return;
        }
        const action = await this.orm.call(
            "doorway.social.inbox",
            "action_create_lead",
            [[this.state.selectedConv.id]]
        );
        if (action) {
            this.action.doAction(action);
        }
        await this._loadConversations();
    }

    setFilterPlatform(val) {
        this.state.filterPlatform = val;
        this._loadConversations();
    }

    setFilterAccount(val) {
        this.state.filterAccount = val;
        this._loadConversations();
    }

    setFilterStatus(val) {
        this.state.filterStatus = val;
        this._loadConversations();
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        this._loadConversations();
    }

    onReplyInput(ev) {
        this.state.replyText = ev.target.value;
    }

    onCommentReplyInput(commentId, ev) {
        this.state.commentReplies[commentId] = ev.target.value;
    }

    setActiveTab(tab) {
        this.state.activeTab = tab;
    }

    get unreadTotal() {
        return this.state.conversations.reduce(
            (s, c) => s + (c.unread_count || 0),
            0
        );
    }

    initials(name) {
        if (!name) {
            return "?";
        }
        return name
            .split(" ")
            .filter(Boolean)
            .map((w) => w[0])
            .join("")
            .substring(0, 2)
            .toUpperCase();
    }

    formatDate(iso) {
        if (!iso) {
            return "";
        }
        try {
            return new Date(iso).toLocaleString("fr-CA", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch {
            return iso;
        }
    }

    platformPrefix(platform) {
        return (platform || "").substring(0, 2);
    }

    platformIcon(platform) {
        return PLATFORM_ICON[platform] || "fa-comment";
    }

    isSelected(conv) {
        return (
            this.state.selectedConv &&
            this.state.selectedConv.id === conv.id
        );
    }

    commentReply(commentId) {
        return this.state.commentReplies[commentId] || "";
    }

    isCommentAiLoading(commentId) {
        return !!this.state.commentAiLoading[commentId];
    }
}

registry.category("actions").add("social_inbox_unified_action", DoorwaySocialInboxView);
