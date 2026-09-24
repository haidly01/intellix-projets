/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { onMounted, onWillUnmount, useEffect } from "@odoo/owl";

const SUPPORT_MODEL = "intellix.support.ticket";
const COPILOT_ACT_PREFIX = "copilot-act-";
const COPILOT_REPLY_PREFIX = "copilot-reply-";

function copilotActionFromElement(el) {
    if (!el?.classList) {
        return null;
    }
    for (const cls of el.classList) {
        if (cls.startsWith(COPILOT_ACT_PREFIX)) {
            return cls.slice(COPILOT_ACT_PREFIX.length);
        }
    }
    return null;
}

function copilotReplyIndexFromElement(el) {
    if (!el?.classList) {
        return null;
    }
    for (const cls of el.classList) {
        if (cls.startsWith(COPILOT_REPLY_PREFIX) && cls !== "copilot-reply-use") {
            return cls.slice(COPILOT_REPLY_PREFIX.length);
        }
    }
    return null;
}

function findTicketFormRoot(el) {
    return el?.closest?.(".o_intellix_support_ticket_form") || null;
}

export class IntellixSupportFormController extends FormController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this._copilotClickHandler = this._onCopilotPanelClick.bind(this);
        this._copilotKeyHandler = this._onCopilotPanelKeydown.bind(this);
        onMounted(() => this._intellixCopilotBind());
        onWillUnmount(() => this._intellixCopilotUnbind());
        useEffect(
            () => {
                this._intellixCopilotClearInput();
            },
            () => [this.model.root.resId]
        );
    }

    _intellixCopilotClearInput() {
        const root = this._intellixCopilotRoot();
        const input = root?.querySelector(".intellix-copilot-input");
        if (input) {
            input.value = "";
        }
    }

    _intellixCopilotRoot() {
        return this.root?.el ? findTicketFormRoot(this.root.el) : null;
    }

    _intellixCopilotBind() {
        const root = this._intellixCopilotRoot();
        if (!root || root.dataset.copilotBound) {
            return;
        }
        root.dataset.copilotBound = "1";
        root.addEventListener("click", this._copilotClickHandler);
        root.addEventListener("keydown", this._copilotKeyHandler);
        this._intellixCopilotEnhanceFooter(root);
        this._intellixCopilotEnhanceTabs(root);
    }

    _intellixCopilotUnbind() {
        const root = this._intellixCopilotRoot();
        if (!root) {
            return;
        }
        root.removeEventListener("click", this._copilotClickHandler);
        root.removeEventListener("keydown", this._copilotKeyHandler);
        delete root.dataset.copilotBound;
    }

    _intellixCopilotEnhanceFooter(root) {
        const footer = root.querySelector(".intellix-copilot-footer");
        if (!footer || footer.dataset.enhanced) {
            return;
        }
        footer.dataset.enhanced = "1";
        const input = footer.querySelector(".intellix-copilot-input");
        const sendBtn = footer.querySelector(".intellix-copilot-send");
        if (input) {
            input.removeAttribute("disabled");
            input.classList.add("intellix-copilot-input-active");
            input.setAttribute("autocomplete", "off");
            input.setAttribute("autocorrect", "off");
            input.setAttribute("autocapitalize", "off");
            input.setAttribute("spellcheck", "false");
            input.setAttribute("data-lpignore", "true");
            input.setAttribute("data-form-type", "other");
            input.value = "";
        }
        if (sendBtn && sendBtn.tagName === "BUTTON") {
            sendBtn.type = "button";
        }
    }

    _intellixCopilotEnhanceTabs(root) {
        const sidebar = root.querySelector(".intellix-support-copilot-sidebar");
        if (!sidebar || sidebar.dataset.tabsEnhanced) {
            return;
        }
        sidebar.dataset.tabsEnhanced = "1";
        const tabs = sidebar.querySelectorAll(".intellix-copilot-notebook .nav-link");
        tabs.forEach((tab) => {
            tab.setAttribute("role", "tab");
        });
    }

    async _onCopilotPanelClick(ev) {
        const root = this._intellixCopilotRoot();
        if (!root || !root.contains(ev.target)) {
            return;
        }

        const actionBtn = ev.target.closest(
            "a.copilot-act-inspect_diagnostic, a.copilot-act-propose_fix, a.copilot-act-propose_fix_auto, a.copilot-act-apply_fix_auto, a.copilot-act-apply_fix, a.copilot-act-approve_fix, a.copilot-act-approve_fix_proposal, a.copilot-act-execute_fix, a.copilot-act-view_campaigns, a.copilot-act-validate_campaign_config, a.copilot-act-create_credits_account, a.copilot-act-assign_credit_plan, a.copilot-act-request_anydesk_id, a.copilot-act-confirm_anydesk_consent, a.copilot-act-open_anydesk_session, a.copilot-act-open_anydesk_tab, a.copilot-act-refresh_diagnostic, [class*='copilot-act-']"
        );
        const actionFromBtn = actionBtn ? copilotActionFromElement(actionBtn) : null;
        if (actionFromBtn) {
            ev.preventDefault();
            ev.stopPropagation();
            await this._copilotRunAction(actionFromBtn);
            return;
        }

        const replyRow = ev.target.closest("[class*='copilot-reply-']");
        const replyIndex = replyRow ? copilotReplyIndexFromElement(replyRow) : null;
        if (replyIndex !== null && replyIndex !== "") {
            ev.preventDefault();
            ev.stopPropagation();
            await this._copilotUseReply(replyIndex);
            return;
        }

        const sendBtn = ev.target.closest(".intellix-copilot-send");
        if (sendBtn && sendBtn.tagName === "BUTTON") {
            ev.preventDefault();
            ev.stopPropagation();
            await this._copilotSendQuestion(root);
        }
    }

    async _onCopilotPanelKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        const root = this._intellixCopilotRoot();
        if (!root) {
            return;
        }
        if (ev.target.matches(".intellix-copilot-input")) {
            ev.preventDefault();
            await this._copilotSendQuestion(root);
            return;
        }
        if (ev.target.closest("[class*='copilot-reply-']")) {
            ev.preventDefault();
            const row = ev.target.closest("[class*='copilot-reply-']");
            const idx = copilotReplyIndexFromElement(row);
            if (idx !== null && idx !== "") {
                await this._copilotUseReply(idx);
            }
        }
    }

    _copilotRecordId() {
        return this.model?.root?.resId;
    }

    async _copilotHandleResult(result) {
        if (!result) {
            return;
        }
        if (result.notify) {
            this.notification.add(result.notify.message, {
                title: result.notify.title,
                type: result.notify.type || "info",
                sticky: Boolean(result.notify.sticky),
            });
        }
        if (result.action) {
            await this.actionService.doAction(result.action);
        }
        if (result.reload && this.model?.root?.resId) {
            await this.model.load({ resId: this.model.root.resId });
        }
        if (result.anydesk_deeplink) {
            try {
                window.open(result.anydesk_deeplink, "_blank");
            } catch (e) {
                if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(result.anydesk_deeplink);
                    this.notification.add(_t("Lien AnyDesk copié."), { type: "info" });
                }
            }
        }
        if (result.suggested_reply && this._copilotInsertComposer(result.suggested_reply)) {
            this.notification.add(_t("Réponse AnyDesk insérée dans le composer."), {
                type: "success",
            });
        }
    }

    async _copilotRunAction(actionCode) {
        const resId = this._copilotRecordId();
        if (!resId) {
            return;
        }
        try {
            const result = await this.orm.call(
                SUPPORT_MODEL,
                "copilot_dispatch_action",
                [[resId], actionCode]
            );
            await this._copilotHandleResult(result);
        } catch (error) {
            this.notification.add(_t("Impossible d'exécuter l'action Copilot."), {
                type: "danger",
            });
            console.error("Copilot action error", error);
        }
    }

    async _copilotUseReply(index) {
        const resId = this._copilotRecordId();
        if (!resId) {
            return;
        }
        try {
            const result = await this.orm.call(
                SUPPORT_MODEL,
                "copilot_get_suggested_reply",
                [[resId], index]
            );
            const text = result?.text || "";
            if (!text) {
                this.notification.add(_t("Réponse suggérée introuvable."), { type: "warning" });
                return;
            }
            if (this._copilotInsertComposer(text)) {
                this.notification.add(_t("Réponse insérée dans le composer."), { type: "success" });
            } else if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
                this.notification.add(_t("Réponse copiée dans le presse-papier."), { type: "info" });
            }
        } catch (error) {
            this.notification.add(_t("Impossible d'utiliser cette réponse."), { type: "danger" });
            console.error("Copilot reply error", error);
        }
    }

    _copilotInsertComposer(text) {
        const root = this._intellixCopilotRoot();
        if (!root) {
            return false;
        }
        const editable = root.querySelector(
            ".o-mail-Composer .odoo-editor-editable[contenteditable='true'], .o-mail-Composer .odoo-editor-editable"
        );
        if (editable) {
            editable.innerText = text;
            editable.dispatchEvent(new InputEvent("input", { bubbles: true }));
            editable.focus();
            return true;
        }
        const textarea = root.querySelector(".o-mail-Composer textarea, .o-mail-Composer-input");
        if (textarea) {
            textarea.value = text;
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            textarea.focus();
            return true;
        }
        return false;
    }

    async _copilotSendQuestion(root) {
        const resId = this._copilotRecordId();
        const input = root.querySelector(".intellix-copilot-input");
        const sendBtn = root.querySelector(".intellix-copilot-send");
        const question = (input?.value || "").trim();
        if (!resId || !question) {
            this.notification.add(_t("Saisissez une question."), { type: "warning" });
            return;
        }
        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.classList.add("intellix-copilot-loading");
        }
        if (input) {
            input.disabled = true;
        }
        try {
            const result = await this.orm.call(SUPPORT_MODEL, "copilot_ask", [[resId], question]);
            const sourceLabel =
                result?.source === "llm" ? _t("Claude") : _t("règles locales");
            if (result?.notify) {
                await this._copilotHandleResult(result);
            } else {
                this.notification.add(
                    _t("Réponse Copilot ajoutée (%s).", sourceLabel),
                    { type: "success" }
                );
            }
            if (input) {
                input.value = "";
            }
            if (result?.reload !== false && this.model?.root?.resId) {
                await this.model.load({ resId: this.model.root.resId });
            }
            const log = root.querySelector(".intellix-copilot-chat-scroll");
            if (log) {
                log.scrollTop = log.scrollHeight;
            }
        } catch (error) {
            this.notification.add(_t("Erreur Copilot — réessayez."), { type: "danger" });
            console.error("Copilot ask error", error);
        } finally {
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.classList.remove("intellix-copilot-loading");
            }
            if (input) {
                input.disabled = false;
                input.focus();
            }
        }
    }
}

export const intellixSupportFormView = {
    ...formView,
    Controller: IntellixSupportFormController,
};

registry.category("views").add("intellix_support_form", intellixSupportFormView);
