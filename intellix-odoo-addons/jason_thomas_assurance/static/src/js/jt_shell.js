/** @odoo-module **/

import { onWillUnmount } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { router, routerBus } from "@web/core/browser/router";
import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

const JT_APP_XMLID = "jason_thomas_assurance.menu_jt_root";
const SIDEBAR_ID = "jt-global-sidebar";

let jtRootMenuId = null;
let jtDashboardActionId = null;
let dashboardLoadTimer = null;
let dashboardOpening = false;

function getActiveActionId() {
    const state = router.current || {};
    const action = state.action;
    if (typeof action === "number") {
        return action;
    }
    const hash = window.location.hash || "";
    const hashMatch = hash.match(/(?:^|[&?])action=(\d+)/);
    if (hashMatch) {
        return parseInt(hashMatch[1], 10);
    }
    const pathMatch = window.location.pathname.match(/action-(\d+)/);
    return pathMatch ? parseInt(pathMatch[1], 10) : null;
}

function isDashboardVisible() {
    return Boolean(
        document.querySelector(".jt-dashboard-page") ||
        document.querySelector(".o_jt_dashboard_form")
    );
}

function isDashboardRouteLoaded() {
    const state = router.current || {};
    return state.model === "jt.dashboard" && typeof state.resId === "number";
}

function updateActiveNav(actionId) {
    const sidebar = document.getElementById(SIDEBAR_ID);
    if (!sidebar) {
        return;
    }
    sidebar.querySelectorAll(".jt-nav-item[data-action-id]").forEach((el) => {
        const id = parseInt(el.dataset.actionId, 10);
        el.classList.toggle("jt-nav-active", Boolean(actionId && id === actionId));
    });
}

function unmountSidebar() {
    document.getElementById(SIDEBAR_ID)?.remove();
}

async function getJtRootMenuId(orm) {
    if (jtRootMenuId) {
        return jtRootMenuId;
    }
    try {
        const [, menuId] = await orm.call(
            "ir.model.data",
            "check_object_reference",
            ["jason_thomas_assurance", "menu_jt_root"],
        );
        jtRootMenuId = menuId || 0;
    } catch {
        jtRootMenuId = 0;
    }
    return jtRootMenuId;
}

async function getDashboardActionId(orm) {
    if (jtDashboardActionId) {
        return jtDashboardActionId;
    }
    try {
        const [, actionId] = await orm.call(
            "ir.model.data",
            "check_object_reference",
            ["jason_thomas_assurance", "action_jt_dashboard"],
        );
        jtDashboardActionId = actionId || 0;
    } catch {
        jtDashboardActionId = 0;
    }
    return jtDashboardActionId;
}

async function isJtApp(orm, menuService) {
    const app = menuService?.getCurrentApp?.();
    if (app?.xmlid === JT_APP_XMLID) {
        return true;
    }
    if ((app?.name || "").includes("Jason Thomas")) {
        return true;
    }
    const rootId = await getJtRootMenuId(orm);
    const menuId = parseInt(browser.sessionStorage.getItem("menu_id") || "0", 10);
    if (rootId && menuId === rootId) {
        return true;
    }
    const model = router.current?.model || "";
    if (model.startsWith("jt.")) {
        return true;
    }
    return false;
}

function isNonDashboardOdooPath() {
    const path = window.location.pathname || "";
    if (/\/odoo\/jt\.(client|police|transaction|activite)(\/|$)/.test(path)) {
        return true;
    }
    if (/\/odoo\/[^/?#]+\/\d+/.test(path) && !path.includes("jt.dashboard")) {
        return true;
    }
    return false;
}

async function shouldLoadDashboard(orm) {
    if (isDashboardVisible() || isDashboardRouteLoaded() || dashboardOpening) {
        return false;
    }
    const state = router.current || {};
    if (state.model && state.model !== "jt.dashboard") {
        return false;
    }
    if (isNonDashboardOdooPath()) {
        return false;
    }
    const activeId = getActiveActionId();
    if (!activeId) {
        const path = window.location.pathname || "";
        return path === "/odoo" || path === "/odoo/" || path.endsWith("/web");
    }
    const dashboardActionId = await getDashboardActionId(orm);
    return Boolean(dashboardActionId && activeId === dashboardActionId);
}

async function openDashboard(env) {
    if (dashboardOpening || isDashboardVisible() || isDashboardRouteLoaded()) {
        return;
    }
    dashboardOpening = true;
    try {
        const action = await env.services.orm.call("jt.dashboard", "action_open_dashboard", []);
        await env.services.action.doAction(action, { clearBreadcrumbs: true });
    } catch (error) {
        console.error("JT dashboard load failed", error);
    } finally {
        dashboardOpening = false;
    }
}

function scheduleDashboardLoad(env) {
    if (dashboardLoadTimer) {
        window.clearTimeout(dashboardLoadTimer);
        dashboardLoadTimer = null;
    }
    dashboardLoadTimer = window.setTimeout(async () => {
        dashboardLoadTimer = null;
        if (!document.body.classList.contains("jt-branded")) {
            return;
        }
        if (await shouldLoadDashboard(env.services.orm)) {
            await openDashboard(env);
        }
    }, 150);
}

function bindSidebarNav(env) {
    const sidebar = document.getElementById(SIDEBAR_ID);
    if (!sidebar || sidebar.dataset.jtBound === "1") {
        return;
    }
    sidebar.dataset.jtBound = "1";
    sidebar.addEventListener("click", async (event) => {
        const link = event.target.closest("a[data-jt-dashboard='1']");
        if (!link) {
            return;
        }
        event.preventDefault();
        await openDashboard(env);
    });
}

async function mountSidebar(orm, env, attempt = 0) {
    if (document.getElementById(SIDEBAR_ID)) {
        updateActiveNav(getActiveActionId());
        bindSidebarNav(env);
        return;
    }
    const actionManager = document.querySelector(".o_web_client .o_action_manager");
    if (!actionManager) {
        if (attempt < 20) {
            window.setTimeout(() => mountSidebar(orm, env, attempt + 1), 100);
        }
        return;
    }
    const actionId = getActiveActionId();
    let html;
    try {
        html = await orm.call("jt.dashboard", "get_sidebar_html", [actionId]);
    } catch (error) {
        console.error("JT sidebar load failed", error);
        return;
    }
    if (!html) {
        return;
    }
    actionManager.insertAdjacentHTML("beforebegin", html);
    updateActiveNav(actionId);
    bindSidebarNav(env);
}

async function syncJtShell(env, { scheduleDashboard = false } = {}) {
    const menuService = env.services.menu;
    const isJt = await isJtApp(env.services.orm, menuService);
    document.body.classList.toggle("jt-branded", isJt);
    if (isJt) {
        await mountSidebar(env.services.orm, env);
        if (scheduleDashboard) {
            scheduleDashboardLoad(env);
        }
    } else {
        unmountSidebar();
        if (dashboardLoadTimer) {
            window.clearTimeout(dashboardLoadTimer);
            dashboardLoadTimer = null;
        }
    }
}

patch(WebClient.prototype, {
    setup() {
        super.setup();
        const env = this.env;
        const refresh = () => syncJtShell(env, { scheduleDashboard: true });
        const onRouteChange = () => {
            syncJtShell(env, { scheduleDashboard: false });
            if (document.body.classList.contains("jt-branded")) {
                updateActiveNav(getActiveActionId());
            }
        };

        env.bus.addEventListener("WEB_CLIENT_READY", refresh, { once: true });
        env.bus.addEventListener("MENUS:APP-CHANGED", refresh);
        routerBus.addEventListener("ROUTE_CHANGE", onRouteChange);
        onWillUnmount(() => {
            routerBus.removeEventListener("ROUTE_CHANGE", onRouteChange);
            if (dashboardLoadTimer) {
                window.clearTimeout(dashboardLoadTimer);
            }
        });
    },
});
