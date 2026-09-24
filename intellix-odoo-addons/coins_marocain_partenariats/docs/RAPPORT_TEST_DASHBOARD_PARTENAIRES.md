# Rapport de test — Dashboard partenaires live

**Date :** 2026-08-12  
**Environnement :** `intellix-dev` / `intellixcrm.com` (DB `intellixcrm`)  
**Module :** `coins_marocain_partenariats` **19.0.1.2.0**  
**Maquette HTML partenaires ITEX :** **branchée** sur `/my/coins-partenaires` (+ OWL backend) — shell dark IntelliX, stats live.

## Périmètre livré

| Élément | Détail |
|---|---|
| Backend | Menu Coins → Partenariats → **Dashboard live** (`ir.actions.client` `coins_partenaires_dashboard`) |
| Portail | `/my/coins-partenaires` (+ `/7` `/30` `/90`) lecture seule |
| JSON | `/coins/partenaires/dashboard/stats` (auth user) |
| Source membres | Tag ITEX **absent** → fallback `coins.entente` statut `active` / `a_renouveler` |
| Répartition | `type_partenaire` (catégories à 0 affichées, pas d’erreur) |
| CRM / Ventes | `crm.lead` / `sale.order` sur `create_date` (période 7/30/90) |
| Cache | Aucun — recalcul à chaque chargement (`as_of` horodaté) |

**Non touché :** tableau de bord natif `coins.overview` (panne séparée).

---

## Données de test créées

| Type | Références | IDs |
|---|---|---|
| Ententes | `ITEX-DEMO-01` influenceur, `ITEX-DEMO-02` agence voyage, `ITEX-DEMO-03` wedding planner | 2, 3, 4 |
| Leads CRM | `[ITEX-DEMO] Lead test 1..3` | 1839, 1840, 1841 |
| Devis Ventes | `ITEX-DEMO-SO-01..03` (client `ITEX Demo Client`) | 16, 17, 18 |

---

## Tests effectués

### T1 — Baseline → après seed (méthode `get_live_dashboard_stats(30)`)

| Métrique | Avant | Après | Observation |
|---|---:|---:|---|
| Partenaires actifs | 0 | **3** | +3 ententes actives |
| Opportunités CRM (30 j) | 245 | **248** | +3 leads |
| Devis / commandes (30 j) | 0 | **3** | +3 sale.order |
| Répartition | tous 0 | influenceur 1, wedding 1, agence 1, congrès 0, autre 0 | OK |

**Résultat : PASS**

### T2 — Périodes configurables

| Période | CRM | Ventes | Membres |
|---|---:|---:|---:|
| 7 j | 49 | 3 | 3 |
| 30 j | 248 | 3 | 3 |
| 90 j | 1445 | 9 | 3 |

Période invalide `"xx"` → fallback 30 j sans exception.

**Résultat : PASS**

### T3 — Champs vides / catégories à zéro

- Catégories sans données (`Organisateur congrès`, `Autre`) affichées avec **0**, pas `undefined` / erreur.
- Template portail utilise `stats.get(...)` avec défauts numériques.

**Résultat : PASS**

### T4 — Compte portail restreint

| Item | Valeur |
|---|---|
| Compte | `portal.demo@intellixcrm.com` (uid 79) — Jean Beaumont (Portail Demo) |
| Groupes | `Role / Portal` + `Portail Partenaire IntelliX` |
| Mot de passe test (session) | `ItexPortalDemo2026!` — **à faire tourner** après démo |
| URL testée | `https://intellixcrm.com/my/coins-partenaires` |

Observations portail (HTML + navigateur 2026-08-12 ~08:54 UTC) :

- Affiche **3 / 248 / 3 / 5 catégories** — aligné avec l’API interne.
- Aucun bouton création lead / devis sur la page.
- Anonyme → page login (pas de fuite des chiffres).
- Pas d’accès admin (`is_admin=False`, `is_system=False`).

**Résultat : PASS** (lecture seule confirmée sur cette vue)

### T5 — Capture écran

Vue portail connectée avec chiffres réels : partenaires 3, CRM 248, ventes 3, répartition avec zéros visibles.  
Horodatage page : `2026-08-12 08:54:17`.

**Résultat : PASS**

---

## Problèmes trouvés / corrigés

| Problème | Correction |
|---|---|
| Tag ITEX inexistant en DB | Fallback documenté sur `coins.entente` (pas de nouveau champ) |
| SSH `intellix-prod` timeout | Déploiement / tests sur instance live `intellixcrm` @ doorway-vps |

---

## Accès partenaire

- Route portail **active** et testée.
- Carte « Tableau de bord partenaires » ajoutée sur `/my` (entrée portail).
- **Lien maquette HTML partenaires du jour : non remplacé.**

---

## Prêt à envoyer aux partenaires (vue Odoo réelle)

**Statut :** prêt techniquement pour envoi **cette semaine**, dès validation métier de ce rapport.

**Horodatage prêt :** **2026-08-12 08:55 UTC** (≈ 09:55 heure Maghreb / 04:55 Toronto).

URL partenaires (remplacement futur de la maquette) :

`https://intellixcrm.com/my/coins-partenaires`

Compte de validation : `portal.demo@intellixcrm.com` (groupes Portail + Portail Partenaire IntelliX).
