/** @odoo-module **/

const AVATAR_COLORS = [
    "#6366f1",
    "#8b5cf6",
    "#ec4899",
    "#f59e0b",
    "#10b981",
    "#06b6d4",
    "#ef4444",
];

export function scoreColor(score) {
    const s = score || 0;
    if (s >= 80) return "#4ade80";
    if (s >= 60) return "#fbbf24";
    return "#f87171";
}

export function initials(name) {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
}

export function avatarColor(id) {
    const idx = (id || 0) % AVATAR_COLORS.length;
    return AVATAR_COLORS[idx];
}

export function trendClass(trend) {
    if (trend === "up") return "ok";
    if (trend === "down") return "warn";
    return "info";
}

export function trendLabel(trend) {
    if (trend === "up") return "↑ Hausse";
    if (trend === "down") return "↓ Baisse";
    return "↔ Stable";
}
