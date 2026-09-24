# Apprentissages — phase pilote Module Hébergement

Ce fichier n’est **pas** un journal technique. Il sert à deux choses :

1. Ne pas perdre un irritant une fois qu’il est corrigé — chaque friction terrain ou choix d’architecture est écrit ici, pas seulement dans le code.
2. Servir plus tard d’argument commercial concret : *« testé et roulé sur X riads pendant Y mois, voici ce qu’on a appris »*, plutôt qu’un pitch théorique.

**Pilote.** Riad Anna Sweety (5 chambres, Kasbah, médina de Marrakech) est le premier établissement. Deux autres riads entreront en rodage une fois le module stable, avant un élargissement commercial plus large.

**Public.** Une personne non technique (Karine) doit pouvoir le lire d’un bout à l’autre.

**Quand ajouter une entrée.** À chaque bug corrigé, changement de comportement suite à un retour terrain, ou décision d’architecture prise en cours de route. Même chose si on *décide de ne pas* faire quelque chose (ex. ne pas créer une société Odoo par riad).

**Format d’une entrée**

```
## [AAAA-MM-JJ] — [Établissement]
**Problème :** ...
**Solution :** ...
**Impact pour les futurs riads clients :** ...
```

Les plus récentes en haut. Pour un choix qui concerne tout le produit, indiquer l’établissement où il a été décidé (aujourd’hui : Anna Sweety).

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Coins Marocain a besoin de savoir si le riad est libre pour un événement, et Coins Québec veut que les créateurs vendent Anna Sweety comme une expérience — sans recoller trois back-offices ni deux moteurs de réservation.

**Solution :** Anna Sweety est listée comme lieu partenaire Coins (fiche partenaire hébergement, signée). Depuis Coins on ouvre le calendrier d'occupation en lecture seule — on ne crée pas de réservation là. Sur la fiche séjour, le champ déjà existant `referral_code` sert de source / code de référence (lien `?promo=`). À la confirmation, on écrit une activation d'entente et on envoie le webhook du versement créateurs déjà en place (séjour offert + 5 %). Pas de fusion des dossiers événement, pas de nouveau moteur de commission.

**Impact pour les futurs riads clients :** On coche le listing partenaire et on colle l'URL de versement. Les créateurs réutilisent le même code promo que Coins. On n'ouvre pas un second back-office.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Une réservation site ou back-office fermait bien les dates dans Coins, mais Channex n'envoyait la fermeture aux OTA qu'au cron de 15 minutes. Jusqu'à un quart d'heure, Booking pouvait encore vendre la chambre — double réservation, pénalité de classement.

**Solution :** À la confirmation (site et back-office), on vide la file Channex tout de suite, comme pour une privatisation. On ne lance pas le full sync. Les résas qui arrivent déjà d'une OTA restent sur le rythme Channex.

**Impact pour les futurs riads clients :** Le prix et la dispo doivent bouger tout de suite. Un cron de 15 minutes n'est pas assez pour l'ouverture Booking.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Le tableau de bord s'ouvrait sur une page crème vide. Les données arrivaient (l'appel serveur répondait) mais la grille CSS Odoo 19 mettait le contenu à hauteur zéro.

**Solution :** On ne touche plus à la colonne flex d’Odoo 19 (`display:block` + `height:auto` sur `.o_web_client` remettait le cadre à hauteur zéro). Le menu vert et l’écran (`position: fixed`) sortent du flux. Les formulaires Odoo (paramètres) restent dans `.o_action_manager`.

**Impact pour les futurs riads clients :** Un écran blanc n'est pas un module cassé — c'est souvent le habillage. On fige le menu hors de la grille hôte.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Un événement et une fiche employé se créaient dans le formulaire Odoo générique. On ne voyait ni la checklist, ni le toggle de privatisation, ni le cumul de rôles (massage + ménage). Salma n'apparaissait pas au planning bien-être.

**Solution :** Deux écrans charte. L'événement choisit un modèle (weekend / mariage / retraite / célébration / aucun), coche les chambres, et le toggle privatisation réutilise le blocage déjà en place — conflits affichés, jamais d'écrasement. L'employé porte plusieurs rôles ; les rôles bien-être ouvrent une fiche prestataire. Le salaire et l'inclusion au rapport partent au comptable.

**Impact pour les futurs riads clients :** On ajoute un rôle (Paramètres) sans toucher au pointage. Un employé multi-casquettes n'a pas besoin de deux fiches.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Le prix pèse sur le classement Booking et Airbnb dès le premier mois. On n'a pas d'API officielle pour lire les concurrents, et scraper les OTA est interdit. Pousser des règles automatiques vers Channex sans historique réel cassera le calendrier.

**Solution :** Phase 1 = visibilité. Anna choisit 5 à 10 riads comparables, recopie le Pace Booking Analytics et Airbnb Insights à la main. Un écart au-delà du seuil (10 % par défaut) envoie un e-mail et, si configuré, un webhook n8n. Rappel hebdo s'il n'y a pas de saisie. Aucune écriture vers `coins.channex.calendar`. Phase 2 (règles internes occupation / saison / délai / durée) attend 3 à 6 mois de données et le pont Odoo → calendrier Channex, déjà identifié comme manquant.

**Impact pour les futurs riads clients :** On active les alertes et on remplit le comp-set local. On ne crée pas un connecteur Booking/Airbnb. Chaque commune / marché a son propre set, jamais un scraping partagé.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** La fiche créneau bien-être ressemblait à un dossier séjour Coins (chauffeur, course, nuits, allergies). On allait recoller deux métiers dans le même formulaire.

**Solution :** Le créneau reste un modèle à part. La maquette (charte papier / laiton / statut) s’applique au soin : Créneau, Voyageuse, Créateur d’Expérience. Chambre et dates du séjour s’affichent en lecture seule si on a lié la réservation. On ne saisit pas le transport ici.

**Impact pour les futurs riads clients :** Un massage n’ouvre pas une course chauffeur. Le dossier Coins garde transferts et allergies.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Les voyageurs écrivent sur Booking, Airbnb, WhatsApp, e-mail et le site. Un agent « bien-être » à part et un autre pour les messages généraux, c’est deux voix, deux files, et Anna qui ne sait plus qui a promis quoi. Un rabais ou une plainte traités tout seuls cassent la relation. Un avis qui n’est jamais demandé pèse moins que les récents sur Booking. Un temps de réponse > 1 h pénalise Airbnb.

**Solution :** Un seul agent — le Créateur d’Expérience. Il répond tout de suite, sans Anna, uniquement avec des faits lus dans Odoo : calendrier, tarifs configurés, script pratique (Kasbah, check-in/out, accès), prise de RDV bien-être. Prix / plainte / privatisation / hors script → Anna, jamais d’improvisation. Après le départ, un message invite à laisser un avis. Le tableau de bord montre le temps de réponse moyen (agent + Anna). Même pattern que Léa : Claude + webhook n8n + modèles du module, pas une nouvelle infra.

**Impact pour les futurs riads clients :** On active l’agent sur l’établissement, on remplit le script local. On ne crée pas un deuxième bot. Les seuils Airbnb (< 5 min / > 1 h) restent visibles pour chaque maison.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Un tableau récapitulatif générique ne se dépose pas à la recette communale. La gérante devrait tout recopier à la main sur le bordereau papier de Marrakech. Le taux Anna Sweety est 25 DH / personne / nuit, et chaque commune a son propre imprimé. La fiche de police (DGSN) n’a rien à voir avec ce versement.

**Solution :** Le trimestre produit un bordereau imprimable aux champs officiels (exploitant, clients, nuitées, montant dû, en lettres, encadré service de l’assiette). Marrakech est un *modèle* configurable, pas un format figé dans le code. Génération au début du mois suivant (jour 5 par défaut), assez tôt pour déposer avant la fin de ce mois. Les fiches de police restent un flux à part.

**Impact pour les futurs riads clients :** On choisit le modèle de la commune et le taux local. On n’imprime pas un formulaire Marrakech pour un riad d’Essaouira ou de Fès.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** La loi marocaine impose une fiche de police par voyageur étranger (24 h) et une taxe de séjour communale, séparée du prix de chambre. Chaque commune a son taux. Le personnel des prochains riads peut être anglophone.

**Solution :** Une fiche par personne (pas par réservation), photo de passeport à l’arrivée, PDF imprimable — pas d’API DGSN tant que le portail n’est pas confirmé. Les fiches ne se suppriment pas (conservation 2 ans). La taxe se calcule toutes seules (personnes × nuits × taux de l’établissement). Anna Sweety : 25 DH / personne / nuit, configurable. Rapport trimestriel par e-mail, comme la paie. Sélecteur FR / EN par utilisateur, pas par maison.

**Impact pour les futurs riads clients :** On configure le taux communal, on n’écrit pas un montant dans le code. La gérante imprime les fiches et les dépose selon la procédure locale. Un réceptionniste anglophone change sa langue sans changer celle de la maison.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Le tableau de bord mettait longtemps à s’afficher. Le menu vert de gauche (Accueil, Réservations…) n’était plus là. Les blocs du centre (occupation, bien-être, inbox) étaient noirs, illisibles — plus du tout la maquette papier / crème.

**Solution :** Le menu latéral se recolle dès qu’on ouvre le module, même par un lien d’action. Les cartes restent blanches, comme sur la maquette : on ne laisse plus le thème sombre d’Odoo les repeindre. L’écran s’affiche d’abord, les chiffres arrivent ensuite — on n’attend plus la boîte réseaux sociaux pour voir l’occupation.

**Impact pour les futurs riads clients :** Le propriétaire juge le produit à l’œil en trois secondes. Si l’écran est noir ou sans menu, il croit que l’outil est cassé. On verrouille la maquette contre le thème du logiciel hôte.

---

## 2026-08-23 — Produit (équipe IntelliX)

**Problème :** En ouvrant le Module Hébergement, la barre d’apps Odoo disparaissait. Karine, Zak, Martin et Michel ne pouvaient plus passer à Coins, au CRM ou aux autres modules — coincés dans le menu vert.

**Solution :** La barre d’apps reste visible pour les managers / l’équipe interne. Seule une réception (groupe Utilisateur, sans Manager) a l’écran immersif. Karine, Zak, Martin et Michel sont managers de ce module et voient Anna Sweety.

**Impact pour les futurs riads clients :** L’équipe Doorway se promène dans toute la plateforme comme ailleurs. La réception d’une maison n’a toujours qu’un seul menu.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Si chaque employé pointe tout seul (ou si l’heure est prise automatiquement), les présences deviennent contestables le jour de la paie : mauvaise heure, oubli, « je n’étais pas en retard ».

**Solution :** La gérante seule pointe, à la main. Chaque matin depuis la carte « Présences aujourd’hui » : Présent / Retard (elle tape l’heure d’arrivée) / Absent (congé planifié, maladie, non justifiée). Elle peut corriger plus tard sur la fiche de l’employé, jusqu’à l’envoi du rapport mensuel. Chaque correction garde qui a changé, quand, et l’ancienne valeur. Aucune horloge ni géolocalisation. Le rapport mensuel au comptable (via doorway_messaging) ne change pas ; une fois envoyé, le mois est clos.

**Impact pour les futurs riads clients :** La paie s’appuie sur ce que la maison a saisi et corrigé, pas sur un badgeage. En cas de question du comptable, l’historique est défendable. Le personnel n’a pas d’app de pointage à installer.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** En quittant le tableau de bord (restaurant, bien-être, événements, personnel), le menu vert disparaissait. Il ne restait que la barre Odoo — et les écrans internes de la maquette n’existaient pas : on tombait sur des listes techniques.

**Solution :** Le menu de gauche reste affiché sur toutes les pages du module. Restaurant, bien-être, événements (liste + coordination jour J) et personnel ont leurs propres écrans, calqués sur la maquette.

**Impact pour les futurs riads clients :** On circule dans le produit comme dans la démo, sans « apprendre Odoo » à chaque clic. La réception retrouve le même menu partout.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Sur le tableau de bord, le personnel voyait deux menus qui disent la même chose : la barre violette d’Odoo en haut, et le menu vert à gauche. On ne savait plus lequel suivre. L’écran paraissait un logiciel d’entreprise, pas l’outil du riad.

**Solution :** Pour le groupe Utilisateur, la barre horizontale d’Odoo est masquée dès qu’on est sur le tableau de bord ou le calendrier. Il ne reste que le menu de gauche (celui de la maquette). Les managers qui ouvrent un autre écran Odoo (listes restaurant, etc.) retrouvent la barre classique.

**Impact pour les futurs riads clients :** La réception n’a pas à « apprendre Odoo ». Un seul menu, le même sur toutes les maisons. On ne forme pas les équipes à la barre technique du logiciel hôte.

---

## 2026-08-23 — Produit (tous les établissements)

**Problème :** Appeler le produit « Module Riad » le cantonnait aux riads. Un hôtel ou une maison d’hôte n’y voyait pas son outil — alors que le back-office est le même (chambres, resto, bien-être, événements).

**Solution :** Le produit s’appelle désormais **Module Hébergement**. Les riads restent le premier marché et le pilote (Anna Sweety), mais le nom dit le métier, pas un type de bâtiment. Les noms techniques internes n’ont pas été touchés.

**Impact pour les futurs riads clients :** Le même produit se vend à un riad, un hôtel ou une maison d’hôte sans « version hôtel » à reconstruire. Le nom commercial ne referme plus le marché avant la démo.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Faut-il isoler chaque riad dans sa propre société Odoo (comme une entreprise séparée, avec sa compta) ou simplement le traiter comme un établissement dans la même base ?

**Solution :** Un riad = un établissement rattaché à son bien existant (chambres, réservations). Pas de société Odoo distincte pour le pilote. Un champ « société » existe déjà, mais il reste optionnel — réservé au jour où un client voudra une isolation comptable complète. Chaque utilisateur ne voit que les établissements qu’on lui a attribués : Anna Sweety ne verra jamais les données d’un autre riad, même s’ils partagent la même plateforme.

**Impact pour les futurs riads clients :** Onboarder un nouveau riad, c’est créer l’établissement, lier le bien, et donner accès aux bonnes personnes. Pas besoin de cloner toute une entreprise dans Odoo. Les deux riads de rodage pourront tourner sur la même instance dès le module stable. Si un groupe hôtelier exige plus tard une compta séparée, on active le champ société — on n’a pas à tout reconstruire.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Le personnel du riad (réception, ménage, cuisine, bien-être, service) a besoin de pointages, d’absences et d’un rapport pour le comptable. La tentation serait de créer un second système RH « rien que pour les riads ».

**Solution :** On réutilise le moteur RH déjà en place (fiches employés, présences, absences). On y ajoute seulement ce qui est propre au riad : l’établissement, le poste, l’heure d’arrivée prévue, le pointage du jour. En fin de mois, un rapport de présences part automatiquement à l’e-mail du comptable **de cet établissement** — pas un comptable unique pour toute la plateforme.

**Impact pour les futurs riads clients :** Une seule fiche par personne, un seul historique de présence. Le jour d’envoi et le destinataire se règlent par maison. On ne promet pas « un logiciel RH en plus » : le personnel du riad entre dans le même socle que le reste d’IntelliX.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Le moteur de présences existant a été pensé pour un call center (pointages liés au composeur d’appels). S’il écrase les pointages du riad chaque nuit, les jours travaillés d’Anna Sweety deviennent faux — et le rapport envoyé au comptable aussi.

**Solution :** Un pointage saisi depuis le Module Hébergement est marqué comme tel. Le traitement automatique du call center ne le remplace plus.

**Impact pour les futurs riads clients :** Le personnel d’un riad n’est pas traité comme des agents d’appels. La paie reste fidèle à ce que la réception a saisi, même si IntelliX sert aussi d’autres métiers sur la même plateforme.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Les événements (privatisation, mariage, groupe) demandent une checklist : chambres, traiteur, créneaux bien-être, terrasse, brief d’équipe. Recréer une messagerie et un suivi des tâches à côté de ce qui existe déjà aurait doublé le travail — et les oublis.

**Solution :** Dossier événement propre au riad (type, dates, formules resto, chambres liées, tables, créneaux bien-être) + modèles de checklist prêts à l’emploi (ex. privatisation weekend). Les rappels d’échéance partent par la messagerie déjà utilisée ailleurs chez Doorway, pas par un second canal e-mail.

**Impact pour les futurs riads clients :** Un mariage ou un groupe se pilote comme un dossier, pas comme une conversation perdue dans WhatsApp. Les modèles se réutilisent ; on les ajuste à la maison, on ne les réécrit pas de zéro. Un seul fil d’e-mails pour l’agence et le riad.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Les réservations chambres passent déjà par Channex (Booking.com et les autres plateformes). Reconstruire ce connecteur « pour le module hébergement » casserait un flux déjà validé.

**Solution :** On n’y touche pas. Le Module Hébergement lit les biens et les réservations existants. Il ajoute le calendrier, le tableau de bord et les usages propres à la maison (terrasse, bien-être, événements). La synchro des disponibilités reste celle qui tourne déjà.

**Impact pour les futurs riads clients :** Un riad déjà sur Channex se branche, il ne « migre » pas ses réservations. Moins de risque d’overbooking le jour de l’ouverture. Argument commercial : on étend un socle qui tourne, on ne promet pas un nouvel outil de channel manager.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Anna Sweety a un compte TikTok (@anna_sweety_coach) qui n’est pas le canal principal de réservation, mais qui doit apparaître dans le back-office. Mettre ce compte en dur dans le produit rendrait le module inutilisable pour le riad suivant.

**Solution :** L’identifiant réseaux sociaux se configure **sur l’établissement**, jamais dans le code. Même logique pour les horaires de terrasse (chez Anna : bien-être 10 h–17 h, restaurant 18 h–23 h) et les noms de chambres / tarifs.

**Impact pour les futurs riads clients :** Chaque maison a son rythme de terrasse, ses chambres, son compte social. Onboarder le 2ᵉ et le 3ᵉ riad, c’est de la configuration, pas une copie du module.

---

## 2026-08-23 — Riad Anna Sweety

**Problème :** Sur la première version de l’écran, le menu latéral (Accueil, Réservations, Restaurant…) s’affichait **au-dessus** du tableau de bord au lieu de rester à gauche. L’écran ne ressemblait plus à la maquette validée — inutilisable au quotidien.

**Solution :** Correction d’affichage pour que le menu reste collé à gauche, comme sur la maquette papier / crème. C’était un conflit avec la mise en page par défaut d’Odoo, pas un choix de contenu.

**Impact pour les futurs riads clients :** Le produit se juge d’abord à l’œil par le propriétaire. On a appris qu’il faut verrouiller la mise en page contre celle du logiciel hôte, sinon chaque mise à jour Odoo peut recasser l’écran. À retester à chaque ouverture d’un nouvel établissement.

---

## Comment tenir ce fichier (pour la suite du pilote)

- Une entrée = un irritant ou une décision, pas une liste de fichiers modifiés.
- Écrire le problème comme Anna (ou le prochain propriétaire) l’a vécu, pas comme le développeur l’a vu.
- La solution tient en quelques phrases. Si on a besoin d’un nom technique, on l’explique entre parenthèses.
- La rubrique **Impact** doit pouvoir se relire dans six mois comme argument commercial : qu’est-ce que le riad n° 4 n’aura plus à subir ?
- Si un irritant revient sur le 2ᵉ ou le 3ᵉ riad alors qu’on le croyait réglé : nouvelle entrée, même si le sujet existe déjà. C’est précisément ce que le rodage doit montrer.
