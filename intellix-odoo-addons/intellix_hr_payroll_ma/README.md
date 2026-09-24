# IntelliX RH — Paie Maroc (`intellix_hr_payroll_ma`)

Module de bulletins de paie marocains pour **Digital Doorway SARL** et entités MA.
S'appuie sur le dossier administratif (`intellix_hr_dossier`) et les contrats IntelliX (`people_engine`).

## Séparation Canada / Maroc

| Pays | Société | Module |
|------|---------|--------|
| Maroc | Digital Doorway SARL | `intellix_hr_payroll_ma` (ce module) |
| Canada | Agence Doorway Inc. | `intellix_hr_payroll_ca` (à venir) |

Les menus **Paie Maroc** ne s'appliquent qu'aux sociétés avec `country_id = MA` ou `x_payroll_ma_enabled`.

## Modèles

- `hr.payroll.structure.ma` — structures Cadre / Non-cadre
- `hr.salary.rule.ma` — règles CNSS, AMO, CIMR, IR (taux en base, non hardcodés)
- `hr.ir.bracket` / `hr.ir.config` — barème IR annuel
- `hr.payslip.ma` / `hr.payslip.line.ma` — bulletins et lignes

## Taux indicatifs (seed)

Les taux par défaut sont **indicatifs** et doivent être mis à jour chaque année via :

- RH → Paie Maroc → Configuration → Règles salariales
- RH → Paie Maroc → Configuration → Tranches IR / Paramètres IR

| Cotisation | Taux seed salarié | Taux seed employeur | Plafond |
|------------|-------------------|---------------------|---------|
| CNSS | 4,48 % | 8,98 % | 6 000 MAD |
| AMO | 2,26 % | 2,26 % | — |
| CIMR | dossier employé | dossier employé | — |
| IR | barème progressif | — | — |

## Intégration people_engine

- Bouton **Générer bulletin MA** sur `pe.employment.contract` actif (CDD/CDI)
- Lit `salaire_base` et période 25→24 via `pe.payroll.service`
- Coexiste avec `pe.payroll.bulletin` (calcul opérationnel call center) sans le remplacer

## Comptabilité

À la validation : écriture dans le journal **Paie MA** (CGNC 61711, 61741, 4432, 4433, 4452).

## Exports

- **CNSS / Damancom** : CSV mensuel (format simplifié — voir gaps)
- **État 9421 IR** : CSV annuel agrégé par employé

## Gaps connus

- `hr_payroll` Enterprise non installé — module autonome
- Odoo 19 utilise `hr.version` (plus `hr.contract`)
- Plan comptable MA partiellement chargé — comptes paie créés au post_init
- Format Damancom exact non implémenté (CSV générique)
- Module Canada `intellix_hr_payroll_ca` non créé
