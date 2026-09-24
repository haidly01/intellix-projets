/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "doorway.extracteur.campaign";

const PAYS = [
    { value: "france", label: "🇫🇷 France" },
    { value: "canada", label: "🇨🇦 Canada" },
    { value: "maroc", label: "🇲🇦 Maroc" },
    { value: "belgique", label: "🇧🇪 Belgique" },
];
const SECTEURS = [
    { value: "assurance", label: "Assurance" },
    { value: "renovation", label: "Rénovation" },
    { value: "immobilier", label: "Immobilier" },
    { value: "telecom", label: "Télécom" },
    { value: "centres_appels", label: "Centres d'appels" },
];
const FREQUENCES = [
    { value: 24, label: "1× / jour" },
    { value: 12, label: "2× / jour" },
    { value: 168, label: "1× / semaine" },
];
const COUT_BADGE = {
    "INTLX-EXT-BRUT": { label: "Brut", cls: "ix-cfg-badge--brut" },
    "INTLX-EXT-VER": { label: "Vérifié", cls: "ix-cfg-badge--ver" },
    "INTLX-EXT-IA": { label: "Qualifié IA", cls: "ix-cfg-badge--ia" },
    "INTLX-EXT-RDV": { label: "RDV", cls: "ix-cfg-badge--rdv" },
};
const DEFAULT_COUT_PAR_LEAD = 0.18;

class ExtracteurConfigurateur extends Component {
    static template = "doorway_leads_bruts.ExtracteurConfigurateur";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.pays = PAYS;
        this.secteurs = SECTEURS;
        this.frequences = FREQUENCES;

        this.state = useState({
            step: 1,
            loadingSources: false,
            loadingAdvice: false,
            deploying: false,
            campaign: {
                nom_campagne: "",
                pays: "france",
                secteur: "assurance",
                zone: "",
                cible: "",
                objectif_leads: 100,
                budget_mensuel: 500,
                frequence_heures: 24,
                signal_intention: "",
                notes_client: "",
            },
            sources: [],
            selectedIds: [],
            advice: null,
            adviceMessage: "",
            coutParLead: DEFAULT_COUT_PAR_LEAD,
            deployResult: null,
        });

        onWillStart(async () => {});
    }

    // -------------------------------------------------- helpers
    get selectedSources() {
        return this.state.sources.filter((s) =>
            this.state.selectedIds.includes(s.registry_id)
        );
    }

    coutBadge(source) {
        return COUT_BADGE[source.cout_estime] || COUT_BADGE["INTLX-EXT-BRUT"];
    }

    stars(n) {
        const full = Math.max(0, Math.min(5, n || 0));
        return { full, empty: 5 - full };
    }

    get tarif() {
        const objectif = Number(this.state.campaign.objectif_leads) || 0;
        const cout = Number(this.state.coutParLead) || DEFAULT_COUT_PAR_LEAD;
        const totalOps = objectif * cout;
        return {
            objectif,
            cout: cout.toFixed(2),
            totalOps: totalOps.toFixed(2),
        };
    }

    // -------------------------------------------------- navigation
    async goToStep(step) {
        if (step === 2 && this.state.sources.length === 0) {
            await this.loadSources();
        }
        this.state.step = step;
    }

    async nextFromStep1() {
        if (!this.state.campaign.nom_campagne.trim()) {
            this.notification.add("Saisissez un nom de campagne.", { type: "warning" });
            return;
        }
        await this.goToStep(2);
    }

    backTo(step) {
        this.state.step = step;
    }

    // -------------------------------------------------- step 2: sources
    async loadSources() {
        this.state.loadingSources = true;
        try {
            const sources = await this.orm.call(MODEL, "get_sources", [
                this.state.campaign.pays,
                this.state.campaign.secteur,
            ]);
            this.state.sources = sources || [];
        } catch (e) {
            this.notification.add("Impossible de charger les sources.", { type: "danger" });
            this.state.sources = [];
        } finally {
            this.state.loadingSources = false;
        }
    }

    toggleSource(source) {
        const id = source.registry_id;
        const idx = this.state.selectedIds.indexOf(id);
        if (idx >= 0) {
            this.state.selectedIds.splice(idx, 1);
        } else {
            this.state.selectedIds.push(id);
        }
    }

    isSelected(source) {
        return this.state.selectedIds.includes(source.registry_id);
    }

    async recommandationIA() {
        this.state.loadingAdvice = true;
        try {
            const res = await this.orm.call(MODEL, "preview_campaign", [
                this._configPayload(),
            ]);
            this.state.adviceMessage = res.message || "";
            if (res.success) {
                this.state.advice = res.advice;
                if (res.advice && res.advice.cout_estime_par_lead) {
                    this.state.coutParLead = res.advice.cout_estime_par_lead;
                }
                // Auto-sélection des sources recommandées par Claude.
                const recommended = res.recommended_ids || [];
                for (const id of recommended) {
                    if (!this.state.selectedIds.includes(id)) {
                        this.state.selectedIds.push(id);
                    }
                }
                this.notification.add("Recommandation IA appliquée.", { type: "success" });
            } else {
                this.notification.add(res.message || "Recommandation IA indisponible.", {
                    type: "warning",
                });
            }
        } catch (e) {
            this.notification.add("Erreur lors de la recommandation IA.", { type: "danger" });
        } finally {
            this.state.loadingAdvice = false;
        }
    }

    async nextFromStep2() {
        if (this.state.selectedIds.length === 0) {
            this.notification.add("Sélectionnez au moins une source.", { type: "warning" });
            return;
        }
        // Coût/lead : avis Claude si dispo, sinon moyenne des formules sélectionnées.
        if (!this.state.advice) {
            const tiers = { "INTLX-EXT-BRUT": 0.12, "INTLX-EXT-VER": 0.18, "INTLX-EXT-IA": 0.28, "INTLX-EXT-RDV": 0.45 };
            const vals = this.selectedSources
                .map((s) => tiers[s.cout_estime])
                .filter((v) => v);
            if (vals.length) {
                this.state.coutParLead = vals.reduce((a, b) => a + b, 0) / vals.length;
            }
        }
        this.state.step = 3;
    }

    // -------------------------------------------------- step 4: deploy
    _configPayload() {
        return {
            ...this.state.campaign,
            name: this.state.campaign.nom_campagne,
            source_ids: this.state.selectedIds,
        };
    }

    async deploy() {
        this.state.deploying = true;
        this.state.step = 4;
        try {
            const res = await this.orm.call(MODEL, "deploy_campaign", [
                this._configPayload(),
            ]);
            this.state.deployResult = res;
            if (res.cout_estime_par_lead) {
                this.state.coutParLead = res.cout_estime_par_lead;
            }
            if (res.success) {
                this.notification.add(res.message || "Campagne déployée.", { type: "success" });
            } else {
                this.notification.add(res.message || "Échec du déploiement.", { type: "warning" });
            }
        } catch (e) {
            this.state.deployResult = {
                success: false,
                message: "Erreur technique lors du déploiement.",
            };
            this.notification.add("Erreur technique lors du déploiement.", { type: "danger" });
        } finally {
            this.state.deploying = false;
        }
    }

    nouvelleCampagne() {
        Object.assign(this.state, {
            step: 1,
            sources: [],
            selectedIds: [],
            advice: null,
            adviceMessage: "",
            coutParLead: DEFAULT_COUT_PAR_LEAD,
            deployResult: null,
            campaign: {
                nom_campagne: "",
                pays: "france",
                secteur: "assurance",
                zone: "",
                cible: "",
                objectif_leads: 100,
                budget_mensuel: 500,
                frequence_heures: 24,
                signal_intention: "",
                notes_client: "",
            },
        });
    }

    openWorkflow() {
        const url = this.state.deployResult && this.state.deployResult.n8n_url;
        if (url) {
            window.open(url, "_blank");
        }
    }

    voirCampagnes() {
        this.action.doAction("doorway_leads_bruts.action_extracteur_campaign_list");
    }
}

registry.category("actions").add("extracteur_configurateur_action", ExtracteurConfigurateur);
