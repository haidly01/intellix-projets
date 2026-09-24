/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebsiteBuilderClientAction } from "@website/client_actions/website_preview/website_builder_action";

patch(WebsiteBuilderClientAction.prototype, {
    onIframeLoad(ev) {
        const iframe = this.websiteContent && this.websiteContent.el;
        // The stock handler dereferences `iframe.contentDocument.body`
        // unconditionally. When the preview iframe is cross-origin or shows a
        // browser-generated error page (blocked frame, redirect loop, etc.),
        // `contentDocument` is null and the unguarded access throws an uncaught
        // error that crashes the entire web client (the user gets stuck and
        // "cannot connect" because the action re-mounts on every reload).
        // Degrade gracefully instead of taking down the backend.
        if (!iframe || !iframe.contentDocument || !iframe.contentDocument.body) {
            return;
        }
        return super.onIframeLoad(ev);
    },
});
