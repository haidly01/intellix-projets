/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const BRIEF_FIELDS = [
    "name",
    "language",
    "business_name",
    "niche",
    "geo",
    "website_url",
    "description",
    "target_keyword",
];

const NAP_FIELDS = [
    "name",
    "address",
    "city",
    "postal_code",
    "country",
    "phone",
    "email",
    "website_url",
    "hours",
    "categories",
    "description",
];

const MODEL = "doorway.seo.workspace";

export class SeoDashboard extends Component {
    static template = "doorway_seo.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            busy: false,
            tab: "pages",
            data: null,
            brief: {},
            nap: {},
            chatInput: "",
            keywordSeed: "",
            selectedIdeas: {},
            showBrief: false,
            search: "",
            newTracked: { keyword: "", target_url: "", location: "", country_code: "ca", language: "fr", device: "desktop" },
        });
        onMounted(() => this.load());
    }

    get wsId() {
        return this.state.data && this.state.data.id;
    }

    // ----- Vue d'ensemble (calculs front-end, aucune donnée inventée) -----
    get pages() {
        return (this.state.data && this.state.data.pages) || [];
    }

    // Pages filtrées par la recherche de la barre supérieure (nom ou URL).
    get filteredPages() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) {
            return this.pages;
        }
        return this.pages.filter(
            (p) =>
                (p.page_name || "").toLowerCase().includes(q) ||
                (p.url || "").toLowerCase().includes(q)
        );
    }

    // Score SEO global = moyenne des scores de pages (0 si aucun audit).
    get overallScore() {
        const p = this.pages;
        if (!p.length) {
            return 0;
        }
        return Math.round(p.reduce((s, x) => s + (x.score || 0), 0) / p.length);
    }

    get overallScoreClass() {
        return this.scoreClass(this.overallScore);
    }

    // Donut conique bleu → teal → violet, rempli au prorata du score.
    get gaugeStyle() {
        const pct = Math.max(0, Math.min(100, this.overallScore));
        const deg = pct * 3.6;
        const a = deg * 0.4;
        const b = deg * 0.7;
        return {
            background:
                `conic-gradient(#2f6bff 0deg ${a}deg, #14b8a6 ${a}deg ${b}deg,` +
                ` #7c3aed ${b}deg ${deg}deg, #e9edf5 ${deg}deg 360deg)`,
        };
    }

    get gaugeCaption() {
        const n = this.pages.length;
        if (!n) {
            return "Lancez un audit pour calculer votre score SEO global.";
        }
        const s = this.overallScore;
        if (s >= 80) return "Excellent — votre site est bien optimisé.";
        if (s >= 50) return "Correct — quelques optimisations restent à appliquer.";
        return "À améliorer — appliquez les recommandations ci-contre.";
    }

    // Cartes de métriques agrégées (onglet On-page), à partir des audits réels.
    get metricCards() {
        const pages = this.pages;
        const n = pages.length;
        if (!n) {
            return [];
        }
        const metric = (f) => pages.map((p) => (p.metrics && p.metrics[f]) || 0);
        const avg = (arr) =>
            arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : 0;
        const count = (fn) => pages.filter(fn).length;

        const titleOk = count((p) => {
            const l = (p.metrics && p.metrics.meta_title_len) || 0;
            return l >= 30 && l <= 60;
        });
        const descOk = count((p) => {
            const l = (p.metrics && p.metrics.meta_desc_len) || 0;
            return l >= 70 && l <= 155;
        });
        const kwPages = count((p) => (p.metrics && p.metrics.keyword_count) || 0);
        const altAvg = avg(metric("alt_coverage"));
        const wordsAvg = avg(metric("word_count"));
        const h1Ok = count((p) => ((p.metrics && p.metrics.h1_count) || 0) === 1);
        const issuesTotal = pages.reduce(
            (s, p) => s + ((p.issues && p.issues.length) || 0),
            0
        );
        const optimized = count((p) => p.state === "optimized");

        const pill = (ok, total) => {
            if (!total) return "neutral";
            const r = ok / total;
            if (r >= 0.8) return "good";
            if (r >= 0.5) return "mid";
            return "bad";
        };

        return [
            {
                key: "title",
                icon: "fa-heading",
                label: "Balises Title",
                value: `${titleOk}/${n}`,
                sub: "longueur optimale",
                pill: pill(titleOk, n),
            },
            {
                key: "desc",
                icon: "fa-align-left",
                label: "Méta descriptions",
                value: `${descOk}/${n}`,
                sub: "longueur optimale",
                pill: pill(descOk, n),
            },
            {
                key: "keywords",
                icon: "fa-key",
                label: "Mots-clés ciblés",
                value: `${kwPages}/${n}`,
                sub: "pages avec mot-clé",
                pill: pill(kwPages, n),
            },
            {
                key: "alt",
                icon: "fa-image",
                label: "Couverture Alt",
                value: `${altAvg}%`,
                sub: "attributs alt des images",
                pill: altAvg >= 80 ? "good" : altAvg >= 50 ? "mid" : "bad",
            },
            {
                key: "h1",
                icon: "fa-header",
                label: "Structure H1",
                value: `${h1Ok}/${n}`,
                sub: "un seul H1 par page",
                pill: pill(h1Ok, n),
            },
            {
                key: "words",
                icon: "fa-file-text-o",
                label: "Volume de contenu",
                value: `${wordsAvg}`,
                sub: "mots en moyenne",
                pill: wordsAvg >= 300 ? "good" : wordsAvg >= 150 ? "mid" : "bad",
            },
            {
                key: "issues",
                icon: "fa-exclamation-triangle",
                label: "Recommandations",
                value: `${issuesTotal}`,
                sub: "anomalies détectées",
                pill: issuesTotal === 0 ? "good" : issuesTotal <= n ? "mid" : "bad",
            },
            {
                key: "optimized",
                icon: "fa-check-circle",
                label: "Pages optimisées",
                value: `${optimized}/${n}`,
                sub: "SEO appliqué",
                pill: pill(optimized, n),
            },
        ];
    }

    // Libellés / styles d'état (badges de pages).
    stateLabel(st) {
        const map = {
            pending: "À auditer",
            audited: "Audité",
            proposed: "Proposition prête",
            optimized: "Optimisé",
            error: "Erreur",
        };
        return map[st] || st || "—";
    }
    stateClass(st) {
        if (st === "optimized") return "dseo_pill--good";
        if (st === "proposed") return "dseo_pill--mid";
        if (st === "error") return "dseo_pill--bad";
        return "dseo_pill--neutral";
    }

    // Initiales / couleur pour les pastilles-avatars des listes.
    initials(txt) {
        const s = (txt || "?").trim();
        const parts = s.split(/[\s\-_.]+/).filter(Boolean);
        if (!parts.length) return "?";
        if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    avatarStyle(txt) {
        const palette = [
            "#2f6bff", "#14b8a6", "#7c3aed", "#f59e0b",
            "#ec4899", "#0ea5e9", "#10b981", "#ef4444",
        ];
        const s = txt || "";
        let h = 0;
        for (let i = 0; i < s.length; i++) {
            h = (h * 31 + s.charCodeAt(i)) % palette.length;
        }
        return { background: palette[h] };
    }

    _apply(payload) {
        this.state.data = payload;
        const brief = {};
        for (const f of BRIEF_FIELDS) {
            brief[f] = payload[f] !== undefined && payload[f] !== null ? payload[f] : "";
        }
        this.state.brief = brief;
        const nap = {};
        const src = payload.nap || {};
        for (const f of NAP_FIELDS) {
            nap[f] = src[f] !== undefined && src[f] !== null ? src[f] : "";
        }
        this.state.nap = nap;
        if (!this.state.keywordSeed && payload.keyword_seed) {
            this.state.keywordSeed = payload.keyword_seed;
        }
    }

    async _call(method, args = []) {
        return this.orm.call(MODEL, method, args);
    }

    async load() {
        this.state.loading = true;
        try {
            this._apply(await this._call("get_or_create_session", []));
        } catch (err) {
            console.error(err);
            this.notification.add("Impossible de charger l'assistant SEO.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    setTab(tab) {
        this.state.tab = tab;
    }
    toggleBrief() {
        this.state.showBrief = !this.state.showBrief;
    }

    async _run(method, args, successMsg) {
        if (!this.wsId || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const payload = await this._call(method, [this.wsId, ...args]);
            this._apply(payload);
            // Solde insuffisant → ouvrir le paywall (achat d'un pack).
            if (payload && payload.paywall) {
                await this.action.doAction(payload.paywall);
                return;
            }
            if (successMsg) {
                this.notification.add(successMsg, { type: "success" });
            }
        } catch (err) {
            console.error(err);
            this.notification.add("L'opération a échoué.", { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    // ----- Brief / NAP -----
    async saveBrief() {
        if (!this.wsId) return;
        const vals = {};
        for (const f of BRIEF_FIELDS) {
            vals[f] = this.state.brief[f];
        }
        try {
            this._apply(await this._call("update_brief", [this.wsId, vals]));
        } catch (err) {
            console.error(err);
        }
    }

    async saveNap() {
        if (!this.wsId) return;
        const vals = {};
        for (const f of NAP_FIELDS) {
            vals[f] = this.state.nap[f];
        }
        try {
            this._apply(await this._call("update_nap", [this.wsId, vals]));
        } catch (err) {
            console.error(err);
        }
    }

    // ----- Chat -----
    async sendChat() {
        const body = (this.state.chatInput || "").trim();
        if (!body || !this.wsId || this.state.busy) {
            return;
        }
        this.state.chatInput = "";
        this.state.busy = true;
        try {
            this._apply(await this._call("run_chat", [this.wsId, body]));
        } catch (err) {
            console.error(err);
            this.notification.add("Message non traité.", { type: "warning" });
        } finally {
            this.state.busy = false;
        }
    }

    onKeydown(ev) {
        // Entrée envoie ; Maj+Entrée insère un saut de ligne.
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendChat();
        }
    }

    // ----- Pages -----
    // Enregistre le site/URL saisi puis lance l'audit (flux « Analyser »).
    async analyzeSite() {
        if (this.state.busy) {
            return;
        }
        await this.saveBrief();
        this.auditPages();
    }
    auditPages() {
        this._run("audit_pages", [this.state.brief.target_keyword || ""], "Audit terminé.");
    }
    optimizeAll() {
        this._run("optimize_all", [], "Propositions générées.");
    }
    optimizePage(id) {
        this._run("optimize_page", [id]);
    }
    applyPage(id) {
        this._run("apply_page", [id, true], "SEO appliqué à la page.");
    }
    setPageKeyword(id, ev) {
        this._run("set_page_keyword", [id, ev.target.value || ""]);
    }

    // ----- Backlinks -----
    generateBacklinks() {
        this._run("generate_backlinks", [], "Cibles de backlinks proposées.");
    }
    generateOutreach(id) {
        this._run("generate_outreach", [id], "Email d'approche généré.");
    }
    setBacklinkStatus(id, ev) {
        this._run("set_backlink_status", [id, ev.target.value]);
    }

    // ----- Citations -----
    seedCitations(priorityOnly) {
        this._run("seed_citations", [priorityOnly], "Citations préparées.");
    }
    addCitation(ev) {
        const id = parseInt(ev.target.value, 10);
        if (id) {
            this._run("add_citation", [id]);
            ev.target.value = "";
        }
    }
    generateCitation(id) {
        this._run("generate_citation", [id], "Contenu de citation généré.");
    }
    setCitationStatus(id, ev) {
        this._run("set_citation_status", [id, ev.target.value]);
    }

    // ----- Keyword research (gratuit) -----
    researchKeywords() {
        const seed = (this.state.keywordSeed || "").trim();
        if (!seed) {
            this.notification.add("Saisissez un mot-clé ou un sujet.", { type: "warning" });
            return;
        }
        this._run("research_keywords", [seed], "Idées de mots-clés générées.");
    }
    analyzeIdea(id) {
        this._run("analyze_keyword_idea", [id]);
    }
    toggleIdea(id) {
        this.state.selectedIdeas[id] = !this.state.selectedIdeas[id];
    }
    saveSelectedKeywords() {
        const ids = Object.keys(this.state.selectedIdeas)
            .filter((k) => this.state.selectedIdeas[k])
            .map((k) => parseInt(k, 10));
        if (!ids.length) {
            this.notification.add("Sélectionnez au moins un mot-clé.", { type: "warning" });
            return;
        }
        this.state.selectedIdeas = {};
        this._run("save_keywords", [ids], "Mots-clés ajoutés au suivi.");
    }

    // ----- Rank tracking (gratuit) -----
    addTracked() {
        const v = this.state.newTracked;
        if (!(v.keyword || "").trim()) {
            this.notification.add("Saisissez un mot-clé à suivre.", { type: "warning" });
            return;
        }
        this._run("add_tracked_keyword", [{ ...v }]);
        this.state.newTracked = { keyword: "", target_url: "", location: "", country_code: "ca", language: "fr", device: "desktop" };
    }
    refreshTracked(id) {
        this._run("refresh_tracked_keyword", [id], "Position rafraîchie.");
    }
    refreshAllTracked() {
        this._run("refresh_all_tracked", [], "Suivi rafraîchi.");
    }
    deleteTracked(id) {
        this._run("delete_tracked_keyword", [id]);
    }

    // Position affichée : 0 = hors top 100.
    posLabel(pos) {
        return pos && pos > 0 ? "#" + pos : "100+";
    }
    deltaClass(dir) {
        if (dir === "up") return "dseo_delta--up";
        if (dir === "down") return "dseo_delta--down";
        if (dir === "new") return "dseo_delta--new";
        return "dseo_delta--flat";
    }
    deltaIcon(dir) {
        if (dir === "up") return "fa fa-arrow-up";
        if (dir === "down") return "fa fa-arrow-down";
        if (dir === "new") return "fa fa-star";
        return "fa fa-minus";
    }
    // Construit les points d'une sparkline SVG (axe Y inversé : #1 en haut).
    sparkPoints(history) {
        const pts = (history || []).filter((h) => h && h.position > 0);
        if (pts.length < 2) {
            return "";
        }
        const W = 220;
        const H = 48;
        const pad = 4;
        const n = pts.length;
        // Échelle 1..max position (borne basse 10 pour lisibilité).
        const maxPos = Math.max(10, ...pts.map((p) => p.position));
        const minPos = 1;
        return pts
            .map((p, i) => {
                const x = pad + (i * (W - 2 * pad)) / (n - 1);
                const ratio = (p.position - minPos) / (maxPos - minPos || 1);
                const y = pad + ratio * (H - 2 * pad); // position 1 → haut
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            })
            .join(" ");
    }

    // ----- Helpers -----
    scoreClass(score) {
        if (score >= 80) return "dseo_score--good";
        if (score >= 50) return "dseo_score--mid";
        return "dseo_score--bad";
    }
    openUrl(url) {
        if (url) {
            window.open(url, "_blank");
        }
    }
    async newSession() {
        try {
            this._apply(await this._call("create_session", []));
            this.notification.add("Nouvel espace SEO créé.", { type: "info" });
        } catch (err) {
            console.error(err);
        }
    }
}

registry.category("actions").add("doorway_seo_dashboard", SeoDashboard);
