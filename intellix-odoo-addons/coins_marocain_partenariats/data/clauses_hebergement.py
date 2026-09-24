# -*- coding: utf-8 -*-
"""Clauses LEGACY (resto / spa / fiches non standard).

Le modèle STANDARD hébergement 2026 (15 % direct / 10 % canal, 2×1 an)
est dans clauses_hebergement_standard.html — chargé seulement si
type_partenaire == hebergement. Ne pas remplacer cette constante par
le HTML standard : resto et spa s'en servent encore.
"""

CLAUSES_HEBERGEMENT_HTML = """
<p><strong>Digital Doorway SARL</strong> — Coins Marocain · Catégorie Hébergement
(hôtels, riads, villas).</p>
<ol>
<li><strong>Objet et durée.</strong> Cette entente régit l'inscription du partenaire
hébergement sur Coins Marocain et l'usage du Channel Manager. Sans durée minimale :
l'inscription reste active jusqu'à résiliation (clause 7). Reconduction tacite
mois après mois.</li>
<li><strong>Services inclus, sans frais fixes.</strong> Fiche partenaire (description,
tarifs, disponibilités) ; Channel Manager (sync Booking.com et/ou Airbnb, blocage
automatique des dates réservées) ; shooting photo/vidéo de l'établissement ;
éligibilité au Carnet du Voyageur et à la roue gagnante. Aucun abonnement fixe
— voir la commission (clause 4).</li>
<li><strong>Comptes Booking.com et Airbnb.</strong> La connexion se fait uniquement
par autorisation officielle (extranet Booking, lien Airbnb). Coins Marocain ne
demande et ne reçoit jamais le mot de passe. Le partenaire reste seul titulaire
de ses comptes et de ses obligations envers ces plateformes. Un seul Channel
Manager automatisé est généralement autorisé par établissement : déconnecter
l'ancien fournisseur avant de connecter Coins Marocain. Coins Marocain n'est
pas responsable des pannes ou changements de politique des plateformes tierces.</li>
<li><strong>Commission.</strong> Réservation via une plateforme connectée
(Booking.com, Airbnb, etc.) : <strong>10&nbsp;%</strong> en plus de la commission
déjà facturée par cette plateforme. Réservation directe via Coins Marocain :
<strong>15&nbsp;%</strong>. Aucun frais fixe. Aucun frais un mois sans réservation
via Coins Marocain.</li>
<li><strong>Facturation.</strong> Commission calculée sur la réservation confirmée
(hors annulations remboursées selon la politique du partenaire). Facture mensuelle
en dh. Paiement via le terminal Intellix si le partenaire y souscrit, sinon
virement ou moyen convenu. Retard : délai de grâce de 7 à 15 jours avant
suspension de la visibilité de la fiche ; le Channel Manager reste actif pendant
ce délai pour éviter les doubles réservations.</li>
<li><strong>Shooting photo/vidéo.</strong> Programmé selon les disponibilités du
partenaire, sans frais. Le partenaire facilite l'accès aux lieux. Le contenu
reste sa propriété ; Coins Marocain a un droit d'usage pour la promotion
(clause 9).</li>
<li><strong>Résiliation.</strong> Préavis 30 jours. La fiche est retirée, le
Channel Manager déconnecté ; le partenaire conserve le contenu photo/vidéo.
Coins Marocain peut suspendre ou résilier en cas de non-paiement, manquement
grave ou fraude (fausses disponibilités, doubles réservations volontaires).</li>
<li><strong>Niveau de service.</strong> Synchronisation en temps réel ou
quasi-temps réel. Support partenaire : réponse sous 24–48 h ouvrées. En cas de
panne du Channel Manager, notification dans les meilleurs délais.</li>
<li><strong>Propriété intellectuelle.</strong> Photos/vidéos : propriété du
partenaire, licence d'usage Coins Marocain (fiche, réseaux, roue gagnante).
Disponibilités et tarifs : propriété du partenaire, usage limité à la sync et
à l'affichage. Marque Coins Marocain et Carnet du Voyageur : Digital Doorway SARL.</li>
<li><strong>Données.</strong> Voyageurs : Loi 09-08 (CNDP, Maroc). Le partenaire
n'utilise pas les coordonnées hors du séjour réservé. Les jetons de connectivité
Channel Manager ne sont jamais partagés avec un tiers.</li>
<li><strong>Responsabilité.</strong> Coins Marocain est un intermédiaire
technologique. La prestation d'hébergement reste celle du partenaire. Plafond :
commissions perçues sur 12 mois, sauf faute lourde ou intentionnelle. Pas de
responsabilité pour les décisions de Booking.com, Airbnb ou autre plateforme tierce.</li>
<li><strong>Force majeure.</strong> Suspension si événement hors contrôle
raisonnable, y compris panne ou changement d'API majeur chez Booking.com,
Airbnb ou un fournisseur d'infrastructure.</li>
<li><strong>Révision.</strong> La commission (clause 4) peut être révisée avec
préavis écrit de 30 jours.</li>
<li><strong>Droit applicable.</strong> Droit marocain, tribunaux de Marrakech
(siège Digital Doorway SARL).</li>
<li><strong>Divers.</strong> Cette entente constitue l'accord complet pour
l'hébergement. Cession interdite sans accord écrit. Notifications par courriel
ou WhatsApp officiel de la fiche.</li>
</ol>
"""
