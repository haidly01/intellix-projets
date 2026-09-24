/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DashboardLoader } from "@spreadsheet_dashboard/bundle/dashboard_action/dashboard_loader_service";

const IX = {
    bg: "#0a0a1a",
    surface: "#1a1a2e",
    surfaceElevated: "#252542",
    surfaceCard: "#2e2e52",
    surfaceCardAlt: "#32325a",
    /** Fond des graphiques Odoo (lisible + axes Chart.js contrastés). */
    chartPlotBg: "#2e2e52",
    text: "#f1f5f9",
    textMuted: "#b8c5d6",
    heading: "#a5b4fc",
    link: "#818cf8",
    primary: "#6366f1",
    success: "#4ade80",
    danger: "#f87171",
    border: "#334155",
};

const ODOO_CHART_TYPES = new Set([
    "odoo_line",
    "odoo_bar",
    "odoo_pie",
    "odoo_geo",
    "odoo_funnel",
    "odoo_scatter",
    "odoo_combo",
    "odoo_waterfall",
    "odoo_treemap",
    "odoo_sunburst",
    "odoo_radar",
]);

const LIGHT_BACKGROUNDS = new Set([
    "#ffffff",
    "#fff",
    "#eff6ff",
    "#fff7ed",
    "#f2f2f2",
    "#f6f7fa",
    "#f5f5f5",
    "#f9fafb",
]);

const DARK_TEXT_COLORS = new Set([
    "#434343",
    "#333333",
    "#333",
    "#374151",
    "#111827",
    "#01666b",
    "#666666",
    "#666",
]);

const TEAL_HEADING_COLORS = new Set(["#01666b", "#01666B", "#0d9488", "#0f766e"]);

const SCORECARD_BACKGROUNDS = [
    IX.surfaceCard,
    IX.surfaceCardAlt,
    IX.surfaceElevated,
    "#2a2a48",
];

const STYLE_OVERRIDES = {
    1: { textColor: IX.heading, fillColor: IX.bg, bold: true, fontSize: 16 },
    2: {
        textColor: IX.text,
        fillColor: IX.surfaceElevated,
        fontSize: 11,
        verticalAlign: "middle",
        bold: true,
    },
    3: { textColor: IX.text, fillColor: IX.surface, verticalAlign: "middle" },
    4: { textColor: IX.text, fillColor: IX.surface, bold: true, fontSize: 11 },
    5: { textColor: IX.textMuted, fillColor: IX.surface, verticalAlign: "middle" },
    6: {
        textColor: IX.text,
        fillColor: IX.surfaceElevated,
        bold: true,
        fontSize: 11,
        align: "center",
    },
    7: {
        textColor: IX.text,
        fillColor: IX.surfaceElevated,
        align: "center",
        fontSize: 11,
        verticalAlign: "middle",
        bold: true,
    },
    8: { textColor: IX.text, fillColor: IX.bg, bold: true },
    9: { fillColor: IX.surface, textColor: IX.text },
};

function normalizeHex(color) {
    if (!color || typeof color !== "string") {
        return "";
    }
    let c = color.trim().toLowerCase();
    if (!c.startsWith("#")) {
        c = `#${c}`;
    }
    return c;
}

function isLightBackground(color) {
    const c = normalizeHex(color);
    if (!c) {
        return false;
    }
    if (LIGHT_BACKGROUNDS.has(c)) {
        return true;
    }
    if (c.length === 7) {
        const r = parseInt(c.slice(1, 3), 16);
        const g = parseInt(c.slice(3, 5), 16);
        const b = parseInt(c.slice(5, 7), 16);
        return (r * 299 + g * 587 + b * 114) / 1000 > 185;
    }
    return false;
}

function remapTextColor(color) {
    const c = normalizeHex(color);
    if (!c) {
        return IX.text;
    }
    if (TEAL_HEADING_COLORS.has(c)) {
        return IX.heading;
    }
    if (DARK_TEXT_COLORS.has(c) || isLightBackground(c)) {
        return IX.text;
    }
    return color;
}

function patchTitle(title) {
    if (!title || typeof title !== "object") {
        return title;
    }
    return {
        ...title,
        color: remapTextColor(title.color),
    };
}

function patchChartDefinition(definition, scorecardIndex) {
    if (!definition || typeof definition !== "object") {
        return definition;
    }
    const def = { ...definition };
    if (def.type === "scorecard" || def.type === "gauge") {
        if (isLightBackground(def.background) || !def.background) {
            def.background =
                SCORECARD_BACKGROUNDS[scorecardIndex % SCORECARD_BACKGROUNDS.length];
        }
    } else if (ODOO_CHART_TYPES.has(def.type)) {
        // Ne pas utiliser IX.surface (= fond page) : Chart.js reprend background pour axes / bordures.
        if (isLightBackground(def.background) || !def.background) {
            def.background = IX.chartPlotBg;
        }
    } else if (isLightBackground(def.background)) {
        def.background = IX.surfaceElevated;
    }
    def.title = patchTitle(def.title);
    if (def.type === "scorecard") {
        def.baselineColorUp = IX.success;
        def.baselineColorDown = IX.danger;
        if (def.baselineDescr && typeof def.baselineDescr === "object") {
            def.baselineDescr = {
                ...def.baselineDescr,
                color: IX.textMuted,
            };
        }
    }
    if (def.chartDefinitions) {
        const chartDefinitions = {};
        for (const [chartId, chartDef] of Object.entries(def.chartDefinitions)) {
            chartDefinitions[chartId] = patchChartDefinition(chartDef, scorecardIndex);
        }
        def.chartDefinitions = chartDefinitions;
    }
    return def;
}

function patchFigureData(data, scorecardIndex) {
    if (!data || typeof data !== "object") {
        return scorecardIndex;
    }
    if (data.chartDefinitions) {
        for (const chartDef of Object.values(data.chartDefinitions)) {
            scorecardIndex = patchFigureData(chartDef, scorecardIndex);
        }
    }
    if (data.type) {
        const patched = patchChartDefinition(data, scorecardIndex);
        Object.assign(data, patched);
        if (data.type === "scorecard") {
            scorecardIndex += 1;
        }
    }
    if (data.title && typeof data.title === "object" && !data.type) {
        data.title = patchTitle(data.title);
    }
    return scorecardIndex;
}

function patchGlobalStyles(styles) {
    if (!styles) {
        return;
    }
    for (const [id, override] of Object.entries(STYLE_OVERRIDES)) {
        if (styles[id]) {
            styles[id] = { ...styles[id], ...override };
        }
    }
    for (const style of Object.values(styles)) {
        if (style.textColor) {
            style.textColor = remapTextColor(style.textColor);
        }
        const isHeaderStyle = style.bold && (style.fontSize ?? 0) >= 11;
        if (!style.fillColor || isLightBackground(style.fillColor)) {
            style.fillColor = isHeaderStyle ? IX.surfaceElevated : IX.surface;
        }
    }
}

function isDashboardSheet(model, sheetId) {
    const name = model.getters.getSheetName(sheetId);
    return name === "Dashboard" || sheetId === "sheet1";
}

function cellContent(model, sheetId, position) {
    try {
        return model.getters.getCell(position)?.content || "";
    } catch {
        return "";
    }
}

/** Listes / pivots / liens odoo:// uniquement (évite de casser le rendu des formules). */
function cellNeedsIntellixTheme(model, sheetId, position) {
    const content = cellContent(model, sheetId, position);
    if (!content) {
        return false;
    }
    return (
        content.includes("ODOO.LIST") ||
        content.includes("PIVOT") ||
        (content.startsWith("[") && content.includes("odoo://"))
    );
}

/** Fond + texte lisible sur listes ODOO.LIST, PIVOT et titres cliquables. */
function applyIntellixDashboardCells(model) {
    for (const sheetId of model.getters.getSheetIds()) {
        if (!isDashboardSheet(model, sheetId)) {
            continue;
        }
        const cells = model.getters.getCells(sheetId);
        for (const cellId of Object.keys(cells)) {
            const position = model.getters.getCellPosition(cellId);
            if (!cellNeedsIntellixTheme(model, sheetId, position)) {
                continue;
            }
            let computed;
            try {
                computed = { ...model.getters.getCellComputedStyle(position) };
            } catch {
                continue;
            }
            const fill = computed.fillColor || "";
            const text = computed.textColor || "";
            const content = cellContent(model, sheetId, position);
            const isLink = content.startsWith("[") && content.includes("odoo://");
            const isHeader =
                computed.bold &&
                (computed.fontSize ?? 0) >= 11 &&
                content.includes("ODOO.LIST.HEADER");
            const needsFill = !fill || isLightBackground(fill);
            const needsText =
                !text ||
                DARK_TEXT_COLORS.has(normalizeHex(text)) ||
                TEAL_HEADING_COLORS.has(normalizeHex(text));
            if (!needsFill && !needsText) {
                continue;
            }
            model.dispatch("UPDATE_CELL", {
                sheetId,
                col: position.col,
                row: position.row,
                style: {
                    ...computed,
                    fillColor: needsFill
                        ? isHeader
                            ? IX.surfaceElevated
                            : IX.surfaceCard
                        : fill,
                    textColor: needsText
                        ? isLink
                            ? IX.link
                            : remapTextColor(text) || IX.text
                        : text,
                },
            });
        }
    }
}

function resetDashboardViewport(model) {
    try {
        model.dispatch("SET_VIEWPORT_OFFSET", { offsetX: 0, offsetY: 0 });
    } catch {
        // ignore if command unavailable
    }
}

function scheduleDashboardThemeRefresh(model) {
    queueMicrotask(() => {
        resetDashboardViewport(model);
        applyIntellixDashboardTheme(model);
        applyIntellixDashboardCells(model);
    });
}

function patchBorders(borders) {
    if (!borders) {
        return;
    }
    for (const border of Object.values(borders)) {
        for (const side of ["top", "bottom", "left", "right"]) {
            if (border[side]?.color && isLightBackground(border[side].color)) {
                border[side].color = IX.border;
            }
            if (border[side]?.color === normalizeHex("#cccccc")) {
                border[side].color = IX.border;
            }
        }
    }
}

/**
 * Thème Intellix sur le snapshot (styles cellules, bordures, figures).
 * Sans cela : titres teal, fonds #f2f2f2 et texte sombre illisibles sur fond sombre.
 */
export function applyIntellixSnapshotTheme(snapshot) {
    if (!snapshot) {
        return snapshot;
    }
    const data = JSON.parse(JSON.stringify(snapshot));
    patchGlobalStyles(data.styles);
    patchBorders(data.borders);
    let scorecardIndex = 0;
    for (const sheet of data.sheets || []) {
        if (sheet.id === "sheet1" || sheet.name === "Dashboard") {
            sheet.areGridLinesVisible = false;
        }
        for (const figure of sheet.figures || []) {
            scorecardIndex = patchFigureData(figure.data, scorecardIndex);
        }
    }
    return data;
}

function updateChartIfNeeded(model, sheetId, figure, chartId, scorecardIndex) {
    if (!chartId) {
        return scorecardIndex;
    }
    let current;
    try {
        current = model.getters.getChartDefinition(chartId);
    } catch {
        return scorecardIndex;
    }
    const patched = patchChartDefinition(current, scorecardIndex);
    const nextIndex = current.type === "scorecard" ? scorecardIndex + 1 : scorecardIndex;
    if (JSON.stringify(patched) !== JSON.stringify(current)) {
        model.dispatch("UPDATE_CHART", {
            chartId,
            definition: patched,
            figureId: figure.id,
            sheetId,
        });
    }
    return nextIndex;
}

/** Re-synchronise les graphiques après chargement (données DB déjà personnalisées). */
export function applyIntellixDashboardTheme(model) {
    let scorecardIndex = 0;
    for (const sheetId of model.getters.getSheetIds()) {
        for (const figure of model.getters.getFigures(sheetId)) {
            if (figure.tag === "chart" && figure.data?.chartId) {
                scorecardIndex = updateChartIfNeeded(
                    model,
                    sheetId,
                    figure,
                    figure.data.chartId,
                    scorecardIndex
                );
            } else if (figure.tag === "carousel" && figure.data?.chartDefinitions) {
                for (const chartId of Object.keys(figure.data.chartDefinitions)) {
                    scorecardIndex = updateChartIfNeeded(
                        model,
                        sheetId,
                        figure,
                        chartId,
                        scorecardIndex
                    );
                }
            }
        }
    }
}

patch(DashboardLoader.prototype, {
    _createSpreadsheetModel(snapshot, revisions = [], currency, translationNamespace) {
        const themedSnapshot = applyIntellixSnapshotTheme(snapshot);
        const model = super._createSpreadsheetModel(
            themedSnapshot,
            revisions,
            currency,
            translationNamespace
        );
        scheduleDashboardThemeRefresh(model);
        const odooDataProvider = model.config?.custom?.odooDataProvider;
        if (odooDataProvider && !model._intellixCellsHooked) {
            model._intellixCellsHooked = true;
            let cellsRefreshTimer = null;
            odooDataProvider.addEventListener("data-source-updated", () => {
                clearTimeout(cellsRefreshTimer);
                cellsRefreshTimer = setTimeout(() => {
                    applyIntellixDashboardCells(model);
                }, 400);
            });
        }
        return model;
    },
});
