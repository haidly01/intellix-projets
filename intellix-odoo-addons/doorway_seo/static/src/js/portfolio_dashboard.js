/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const SUMMARY_FIELDS = [
    "site_id", "domain", "label", "period_days", "traffic_ok",
    "clicks", "impressions", "ctr", "position",
    "clicks_delta_pct", "impressions_delta_pct", "ctr_delta_pct", "position_delta_pct", "period_comparable",
    "top_queries_json",
    "geo_mentioned", "geo_total", "geo_score_label", "faqpage", "last_blog_label",
    "testimonials_label", "nap_phone", "yaml_label",
    "citations_human_done", "citations_human_objective",
    "citations_self_done", "citations_self_objective", "citations_status_label",
    "pages_audited", "issues_count", "status_label", "status_class",
    "health_lines_json", "next_action", "captured_at",
];

const BUCKET_ORDER = ["1-3", "4-10", "11-20", "21-50", "50+"];

export class PortfolioDashboard extends Component {
    static template = "doorway_seo.PortfolioDashboard";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            view: "overview",
            selectedSite: null,
            period: 90,
            category: "tout",
            selectedSiteIds: [],
            search: "",
            summaries: [],
            chantiers: {},
            keywordsBySite: {},
            keywordsLoading: false,
        });
        onMounted(() => this.load());
    }

    async load() {
        this.state.loading = true;
        const [summaries, chantierRows] = await Promise.all([
            this.orm.searchRead("doorway.seo.site.summary", [], SUMMARY_FIELDS),
            this.orm.searchRead(
                "doorway.seo.portfolio.audit",
                [],
                ["site_id", "chantier", "metric", "value_float", "value_text", "detail"],
                { order: "captured_at desc", limit: 5000 }
            ),
        ]);
        this.state.summaries = summaries;

        // Le modèle EAV accumule l'historique — on garde la 1ère occurrence
        // par (site, chantier, métrique), l'ordre par défaut étant captured_at desc.
        const chantiers = {};
        for (const row of chantierRows) {
            chantiers[row.site_id] ||= {};
            chantiers[row.site_id][row.chantier] ||= {};
            if (!(row.metric in chantiers[row.site_id][row.chantier])) {
                chantiers[row.site_id][row.chantier][row.metric] = { value: row.value_float, text: row.value_text, detail: row.detail };
            }
        }
        this.state.chantiers = chantiers;
        this.state.loading = false;
    }

    // ----- Filtres -----
    setPeriod(p) {
        this.state.period = p;
    }
    setCategory(c) {
        this.state.category = c;
    }
    toggleSite(siteId) {
        const i = this.state.selectedSiteIds.indexOf(siteId);
        if (i === -1) this.state.selectedSiteIds.push(siteId);
        else this.state.selectedSiteIds.splice(i, 1);
    }
    isSiteToggled(siteId) {
        return this.state.selectedSiteIds.includes(siteId);
    }
    clearSiteFilter() {
        this.state.selectedSiteIds.splice(0, this.state.selectedSiteIds.length);
    }

    // ----- Données dérivées : vue d'ensemble -----
    get allSiteIds() {
        return [...new Set(this.state.summaries.map((r) => r.site_id))].sort();
    }

    rowFor(siteId, period) {
        return this.state.summaries.find((r) => r.site_id === siteId && r.period_days === period);
    }

    siteLabel(siteId) {
        const row = this.rowFor(siteId, 90);
        return (row && (row.label || row.domain)) || siteId;
    }

    get filteredSiteIds() {
        const q = this.state.search.trim().toLowerCase();
        return this.allSiteIds.filter((sid) => {
            if (this.state.selectedSiteIds.length && !this.state.selectedSiteIds.includes(sid)) return false;
            if (q) {
                const row = this.rowFor(sid, this.state.period);
                const hay = ((row && row.domain) || sid) + " " + ((row && row.label) || "");
                if (!hay.toLowerCase().includes(q)) return false;
            }
            return true;
        });
    }

    get filteredSites() {
        return this.filteredSiteIds.map((sid) => this.rowFor(sid, this.state.period)).filter(Boolean);
    }

    get kpis() {
        const rows = this.filteredSites;
        const clicks = rows.reduce((s, r) => s + (r.clicks || 0), 0);
        const impressions = rows.reduce((s, r) => s + (r.impressions || 0), 0);
        const withTraffic = rows.filter((r) => r.traffic_ok && r.clicks > 0).length;
        let top = null;
        for (const r of rows) {
            if (!top || (r.clicks || 0) > (top.clicks || 0)) top = r;
        }
        return {
            clicks,
            impressions,
            withTraffic,
            total: rows.length,
            topLabel: top && top.clicks > 0 ? top.label || top.domain : "—",
        };
    }

    get geoTop() {
        return [...this.filteredSites]
            .filter((r) => r.geo_total > 0)
            .sort((a, b) => b.geo_mentioned / (b.geo_total || 1) - a.geo_mentioned / (a.geo_total || 1))
            .slice(0, 6);
    }

    get citationsSummary() {
        const rows = this.filteredSites;
        const humanDone = rows.reduce((s, r) => s + (r.citations_human_done || 0), 0);
        const humanObj = rows.reduce((s, r) => s + (r.citations_human_objective || 0), 0);
        const selfDone = rows.reduce((s, r) => s + (r.citations_self_done || 0), 0);
        const selfObj = rows.reduce((s, r) => s + (r.citations_self_objective || 0), 0);
        const pending = rows.filter(
            (r) =>
                r.citations_human_done < r.citations_human_objective ||
                r.citations_self_done < r.citations_self_objective
        );
        return { humanDone, humanObj, selfDone, selfObj, pending };
    }

    showSection(name) {
        return this.state.category === "tout" || this.state.category === name;
    }

    // ----- Navigation -----
    openSite(siteId) {
        this.state.selectedSite = siteId;
        this.state.view = "detail";
        this.loadKeywordsFor(siteId);
    }
    backToOverview() {
        this.state.view = "overview";
        this.state.selectedSite = null;
    }

    async loadKeywordsFor(siteId) {
        if (this.state.keywordsBySite[siteId]) return;
        this.state.keywordsLoading = true;
        const rows = await this.orm.searchRead(
            "doorway.seo.keyword.position",
            [["site_id", "=", siteId]],
            ["query", "position", "clicks", "impressions", "bucket"],
            { order: "position asc" }
        );
        this.state.keywordsBySite[siteId] = rows;
        this.state.keywordsLoading = false;
    }

    // ----- Fiche site -----
    get detailRow() {
        return this.rowFor(this.state.selectedSite, this.state.period);
    }
    get detailChantiers() {
        return this.state.chantiers[this.state.selectedSite] || {};
    }
    get detailTopQueries() {
        const row = this.detailRow;
        if (!row || !row.top_queries_json) return [];
        try {
            return JSON.parse(row.top_queries_json) || [];
        } catch {
            return [];
        }
    }
    get detailHealthLines() {
        const row = this.detailRow;
        if (!row || !row.health_lines_json) return [];
        try {
            return JSON.parse(row.health_lines_json) || [];
        } catch {
            return [];
        }
    }
    get detailKeywordsReady() {
        return !!this.state.keywordsBySite[this.state.selectedSite];
    }
    get detailBuckets() {
        const kp = this.detailChantiers.keyword_positions || {};
        const kwRows = this.state.keywordsBySite[this.state.selectedSite] || [];
        const maxCount = Math.max(1, ...BUCKET_ORDER.map((b) => (kp["bucket_" + b] || {}).value || 0));
        return BUCKET_ORDER.map((b) => {
            const count = (kp["bucket_" + b] || {}).value || 0;
            return {
                id: b,
                count,
                pct: Math.round((count / maxCount) * 100),
                keywords: kwRows.filter((k) => k.bucket === b),
                hasSourceData: this.detailKeywordsReady,
            };
        });
    }
    get chantier1() {
        const c = this.detailChantiers.render_health || {};
        return { pagesChecked: (c.pages_checked || {}).value || 0, findings: (c.findings_count || {}).value || 0 };
    }
    get chantier2() {
        const c = this.detailChantiers.content_dilution || {};
        return {
            pagesCrawled: (c.pages_crawled || {}).value || 0,
            uniquenessScore: (c.uniqueness_score || {}).value || 0,
            cannibalization: (c.cannibalization_count || {}).value || 0,
            neverClicked: (c.pages_never_clicked_count || {}).value || 0,
            // top 5 des pires paires : une ligne « requête | A: URL | B: URL | impressions »
            cannibTop: ((c.cannibalization_top5 || {}).detail || "").split("\n").filter(Boolean),
        };
    }
    get chantier4() {
        const c = this.detailChantiers.lead_attribution || {};
        return { leads: (c.leads_90d || {}).value || 0 };
    }

    // ----- Recommandations (règles simples v1, basées sur les données existantes) -----
    get recommendations() {
        const groups = { sante: [], presence: [], positionnement: [] };
        const row = this.detailRow;
        if (!row) return groups;
        const c2 = this.chantier2;

        if (row.issues_count > 0) {
            groups.sante.push(`${row.issues_count} problème(s) technique(s) actif(s) à corriger en priorité.`);
        } else {
            groups.sante.push("Aucun problème technique actif détecté — maintenir la vigilance.");
        }
        if (c2.cannibalization > 0) {
            groups.sante.push(
                `${c2.cannibalization} pages se cannibalisent entre elles — clarifier quelle page cibler par mot-clé.`
            );
        }
        if (c2.neverClicked > 0) {
            groups.sante.push(
                `${c2.neverClicked} pages n'ont reçu aucun clic récent — évaluer une fusion ou une désindexation.`
            );
        }

        const geoRatio = row.geo_total > 0 ? row.geo_mentioned / row.geo_total : null;
        if (geoRatio === null) {
            groups.presence.push("Visibilité IA non encore mesurée pour ce site.");
        } else if (geoRatio < 0.5) {
            groups.presence.push(
                `Visibilité IA faible (${row.geo_mentioned}/${row.geo_total} requêtes valident une citation) — enrichir FAQ / preuves sociales.`
            );
        } else {
            groups.presence.push(
                `Bonne visibilité IA (${row.geo_mentioned}/${row.geo_total} requêtes) — maintenir le contenu à jour.`
            );
        }
        const humanPending = Math.max((row.citations_human_objective || 0) - (row.citations_human_done || 0), 0);
        const selfPending = Math.max((row.citations_self_objective || 0) - (row.citations_self_done || 0), 0);
        if (humanPending > 0 || selfPending > 0) {
            groups.presence.push(`${humanPending + selfPending} citation(s) / annuaire(s) en attente de soumission.`);
        }

        const buckets = this.detailBuckets;
        const total = buckets.reduce((s, b) => s + b.count, 0);
        const b1120 = buckets.find((b) => b.id === "11-20");
        const b50 = buckets.find((b) => b.id === "50+");
        if (b1120 && b1120.count > 0) {
            groups.positionnement.push(
                `${b1120.count} mot(s)-clé(s) en position 11-20 — à portée d'un gain rapide vers la 1ère page.`
            );
        }
        if (b50 && total > 0 && b50.count / total > 0.3) {
            groups.positionnement.push(
                `${b50.count} mot(s)-clé(s) au-delà de la position 50 (${Math.round(
                    (b50.count / total) * 100
                )}% du portefeuille) — prioriser les requêtes proches du top 20 avant celles-ci.`
            );
        }
        if (!groups.positionnement.length) {
            groups.positionnement.push("Distribution des positions équilibrée — pas d'action prioritaire identifiée.");
        }

        return groups;
    }

    // ----- Formatage -----
    fmtNum(n) {
        return new Intl.NumberFormat("fr-CA").format(Math.round(n || 0));
    }
    fmtPos(n) {
        const v = Number(n);
        return Number.isFinite(v) ? v.toFixed(1) : "—";
    }
    fmtDelta(pct, comparable = true) {
        if (!comparable || pct === null || pct === undefined) return "n.d.";
        const sign = pct > 0 ? "+" : "";
        return `${sign}${pct.toFixed(1)}%`;
    }
    deltaClass(pct, comparable = true) {
        if (!comparable) return "pdb_flat";
        if (!pct) return "pdb_flat";
        return pct > 0 ? "pdb_up" : "pdb_down";
    }
    fmtCapturedAt(raw) {
        // Odoo renvoie "YYYY-MM-DD HH:MM:SS" en UTC sans suffixe — affiché
        // brut jusqu'ici (rapport SEO du 23 sept, bug #9). On le reparse en
        // UTC explicite puis on affiche en heure locale du navigateur.
        if (!raw) return "—";
        const d = new Date(String(raw).replace(" ", "T") + "Z");
        if (Number.isNaN(d.getTime())) return String(raw);
        return d.toLocaleString("fr-CA", {
            day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
        });
    }
    statusChipClass(cls) {
        return "pdb_chip pdb_chip--" + (cls || "neutral");
    }
}

registry.category("actions").add("doorway_seo_portfolio_dashboard", PortfolioDashboard);
