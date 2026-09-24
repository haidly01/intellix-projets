/** @odoo-module **/

const SELECTOR = [
    ".o_coins_pipeline_kanban",
    ".o_coins_fiche",
    ".o_coins_fiche_sheet",
    ".o_coins_overview_dashboard",
    ".o_coins_dashboard",
    ".o_coins_part_backend_dash",
].join(",");

function syncCoinsTheme() {
    const on = Boolean(document.querySelector(SELECTOR));
    document.documentElement.classList.toggle("o_coins_light_pipeline", on);
}

function start() {
    syncCoinsTheme();
    if (!document.body) {
        return;
    }
    new MutationObserver(syncCoinsTheme).observe(document.body, {
        childList: true,
        subtree: true,
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}
