/** @odoo-module **/

import { DoorwayCrmWebmail } from "@doorway_crm/js/doorway_webmail";

const originalSetup = DoorwayCrmWebmail.prototype.setup;
DoorwayCrmWebmail.prototype.setup = function () {
    originalSetup.call(this);
    this.actionParams = this.props.action?.params || {};
};

function pickOwnMailboxId(mailboxes) {
    const boxes = mailboxes || [];
    const mine = boxes.filter((m) => m.is_owner);
    const picked =
        mine.find((m) => m.is_default) ||
        mine.find((m) => m.message_count > 0) ||
        mine[0] ||
        boxes.find((m) => m.is_default) ||
        boxes[0];
    return picked ? picked.id : null;
}

const originalInit = DoorwayCrmWebmail.prototype._init;
DoorwayCrmWebmail.prototype._init = async function () {
    await originalInit.call(this);
    const requestedId = this.actionParams?.mailbox_id;
    if (!requestedId && this.state.mailboxes?.length) {
        const ownId = pickOwnMailboxId(this.state.mailboxes);
        if (ownId && ownId !== this.state.selectedMailboxId) {
            this.state.selectedMailboxId = ownId;
            if (typeof this._loadMessages === "function") {
                await this._loadMessages();
            }
        }
    }
    if (this.actionParams?.mode === "compose") {
        this.openCompose();
    }
};
