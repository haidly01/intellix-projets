# Rapport intake — lot Riad Asrari (corrections 2026-09-09)

Le pipeline reste **générique**. Ce lot a été lancé avec `--slug riad-asrari`.
Aucun Ken Burns / DepthFlow, aucune fiche publique, aucun pin carte.

## 1. Contact Drive — faute de frappe, dossier Asrari uniquement

Adresse signalée dans l'intake : `addjemanna@gmail.com` (aucune fiche exacte).

Adresse **corrigée** par Karine : `riaddjemanna@gmail.com`.

**Consigne Karine :** ce contact n'a **aucun lien** avec le partenariat Riad Djemanna. Ce sont deux riads et deux dossiers distincts, malgré la ressemblance du nom dans l'adresse (pseudo personnel, sans rapport). Ne pas fusionner, ne pas rapprocher, ne pas croiser les infos.

| Dossier | Partenaire | Lead | Entente | Mail partenariat |
|---|---|---|---|---|
| **Riad Asrari** (ce lot) | 21142 Serge et Charaf | 20121 | ENT/2026/0019 | `riadasrarimbi@gmail.com` |
| Riad Djemanna (autre riad) | 21237 + 20842 Abdelhadi | 2657 | ENT/2026/0015 | `riaddjemanna@gmail.com` |

Correction faite **uniquement** sur Asrari :

- Intake France `meta.json` : `drive_contact_email` = `riaddjemanna@gmail.com` (typo corrigée). Le mail partenariat `contact_email` reste `riadasrarimbi@gmail.com` (entente déjà envoyée à cette adresse).
- CRM : note interne sur le lead 20121 et le commentaire du partenaire 21142. **Aucun** champ e-mail de Djemanna (21237 / 20842 / lead 2657) n'a été modifié. Pas de fusion, pas de `parent_id` croisé.

La première lecture CRM avait traité `riaddjemanna@gmail.com` comme une correspondance Djemanna (même chaîne). Karine infirme ce rapprochement. L'homonymie d'adresse ne crée pas de lien métier.

## 2. Booking.com

HTTP direct (Chrome + Safari, depuis cet agent et depuis le VPS France) : **202 WAF** (challenge JS). Pas de scraping intensif.

Repli **une** requête lecteur de page (`r.jina.ai`) : contenu de `https://www.booking.com/hotel/ma/riad-asrari.fr.html` récupéré.

Faits retenus (matière première, pas à citer) :

- **6** options d'hébergement distinctes (IDs RD 27455101–105 et 27455108)
- Piscine extérieure, wifi, clim, petit-déjeuner, restaurant, hammam/spa, terrasse, réception 24h/24, navette aéroport
- Adresse : 42, Derb Derdouba, Médina, 40000 Marrakech

**Encore manquant / à coller par Karine si elle le voit sur la fiche :**

1. Confirmation que les 6 options = **6 chambres physiques** (pas 2 unités du même type)
2. Capacité totale (nombre de personnes)
3. Piscine chauffée ou non, saison / horaires
4. Nombre exact de salles de bains si un chiffre global est affiché

## 3. Piscine — photos recatégorisées

La catégorie `piscine` était **déjà** dans le schéma vision. Le modèle a classé le bassin de nage du patio en `commun` (cour).

Photos inspectées (JPEG France `/opt/partners-intake/riad-asrari/photos-brutes/`) :

| Fichier | Avant | Après | Motif |
|---|---|---|---|
| WhatsApp Image 2026-09-09 at 08.29.28.jpeg | commun | **piscine** | Plunge pool turquoise, sujet principal |
| WhatsApp Image 2026-09-09 at 08.29.42.jpeg | commun | **piscine** | Marches d'accès dans l'eau |
| WhatsApp Image 2026-09-09 at 08.29.43 (1).jpeg | commun | **piscine** | Bassin de nage, patio |
| WhatsApp Image 2026-09-09 at 08.29.44 (1).jpeg | commun | **piscine** | Piscine centrale, arcades |
| WhatsApp Image 2026-09-09 at 08.29.44.jpeg | commun | **piscine** | Même bassin, autre angle |

Piscine **visible en arrière-plan** (catégorie inchangée, sujet = terrasse) :

- `WhatsApp Image 2026-09-09 at 08.29.50.jpeg` → commun
- `WhatsApp Image 2026-09-09 at 08.29.50 (5).jpeg` → exterieur

Catégories après correction : **piscine 5**, commun 16, chambre 14, détail 4, extérieur 2.

Prompt vision : règle explicite ajoutée (bassin nageable = `piscine`, pas `commun` ; fontaine ornementale reste `commun`). Test unitaire : `test_piscine_is_explicit_vision_category`.

## Photos / coût (inchangé)

| | |
|---|---|
| Dossier Drive | `1Pxhp3ktQ0sRgKKkmkJV-bYyd1LnZdk8r` |
| JPEG | **41** |
| Appels vision | 41 (non relancés pour cette correction) |
| Coût vision | **~0,115 USD** + fiche ~0,007 USD |

## Validation humaine

Aucun job motion. Page `/intake-photos/` noindex. JPEG non publiés.
