# Comptabilité Maroc IntelliX (`intellix_account_ma`)

Configuration CGNC pour **Digital Doorway SARL** (Maroc), séparée de la comptabilité Canada (**Agence Doorway Inc.**).

> **Important — Devis/facture Canada → comptabilité Canada.**  
> Les clients canadiens sont routés automatiquement vers Agence Doorway Inc. (plan `l10n_ca`).  
> Les clients marocains et l'export de services depuis le Maroc passent par Digital Doorway SARL.

## Routage devis / factures (MA ↔ CA)

| Pays client | Société | Position fiscale |
|-------------|---------|------------------|
| MA (Maroc) | Digital Doorway SARL | Maroc — TVA 20 % |
| CA (Canada) | Agence Doorway Inc. | Taxes Canada (`l10n_ca`) |
| FR, BE, CH, US, etc. | Digital Doorway SARL | Export de services — TVA 0 % |

Priorité de résolution : `x_billing_company_id` sur le contact → pays → société du contact → défaut Maroc (export).

Override manuel : champ **Société de facturation** sur la fiche contact (`x_billing_company_id`).


| Société | Pays | Plan | Module |
|---------|------|------|--------|
| Digital Doorway SARL | MA | CGNC (`l10n_ma`) | `intellix_account_ma` |
| Agence Doorway Inc. | CA | Canada (`l10n_ca`) | *(comptabilité standard Odoo)* |

## Comptes clés (CGNC 6 chiffres — indicatif)

| Spec | Code CGNC | Usage IntelliX |
|------|-----------|----------------|
| 7124 | 712420 | Licences SaaS / études |
| 7125 | 712430 | VoIP, crédits IA, extracteur |
| 7126 | 712720 | Marketing géré |
| 7127 | 712420 | Setup / formation |
| 3421 | 342110 | Clients |
| 4411 | 441110 | Fournisseurs |
| 4455 | 445500 | TVA facturée |
| 34552 | 345520 | TVA récupérable charges |
| 5141 | 514100 | Banques |
| 6171 / 6174 | 617110 / 617410 | Paie (aligné `intellix_hr_payroll_ma`) |
| 4441 / 4452 | 444100 / 445200 | CNSS / IR |

Valider les comptes et taux avec votre comptable avant clôture.

## Positions fiscales (Maroc)

- **Maroc** — TVA 20 % (prestations de services)
- **Export de services** — TVA 0 % / exonération art. 92 CGI pour clients hors Maroc (FR, BE, CH, CA, etc.)

## Analytique — plan « Modules Intellix »

| Compte | Module |
|--------|--------|
| ANA-SALES | Sales / Call Center / VoIP / IA |
| ANA-RH | RH |
| ANA-FORM | Formation / setup |
| ANA-MKT | Marketing |
| ANA-TM | Traffic Manager |
| ANA-EXT | Extracteur |

## Dépendances

- `l10n_ma` (Odoo 19 — disponible)
- `intellix_catalog`, `intellix_hr_dossier`, `intellix_hr_payroll_ma`

## Gaps connus

- Plan CGNC complet chargé via `account.chart.template` si absent (< 50 comptes).
- Codes spec 4 chiffres (7124…) mappés vers CGNC 6 chiffres Odoo 19.
- Catégories Marketing / Services mappées en post-init (pas d'XML ID catalogue).
- Module paie Canada (`intellix_hr_payroll_ca`) non créé.
