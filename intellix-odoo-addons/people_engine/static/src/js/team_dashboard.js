/** @odoo-module **/

import { scoreColor, initials, avatarColor, trendClass, trendLabel } from "./team_dashboard_utils";

export { scoreColor, initials, avatarColor, trendClass, trendLabel };

export function employeesByBand(employees) {
    const list = employees || [];
    return {
        watch: list.filter((e) => (e.people_score || 0) < 60),
        growing: list.filter((e) => (e.people_score || 0) >= 60 && (e.people_score || 0) < 80),
        top: list.filter((e) => (e.people_score || 0) >= 80),
    };
}

export function bandStats(employees) {
    const all = employees || [];
    const avg = all.length
        ? Math.round(all.reduce((s, e) => s + (e.people_score || 0), 0) / all.length)
        : 0;
    return {
        total: all.length,
        avg,
        watch: all.filter((e) => (e.people_score || 0) < 60).length,
        alerts: all.reduce((s, e) => s + (e.people_alerts_count || 0), 0),
    };
}
