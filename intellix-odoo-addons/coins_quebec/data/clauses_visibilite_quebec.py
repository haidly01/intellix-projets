# -*- coding: utf-8 -*-
"""Clauses visibilité Coins Québec — resto / spa / activité / boutique (pas l'hébergement).

L'hébergement garde CLAUSES_HEBERGEMENT_QUEBEC_HTML (Channel Manager).
Ici : fiche + commission. Le shooting n'est pas inclus.
"""


def cq_visibilite_clauses_html(categorie, commission_pct):
    """Texte signable. Doit contenir « Agence Doorway » et « Coins Québec »
    pour que coins.entente ne le remplace pas par les clauses hôtel.
    """
    pct = int(commission_pct)
    return """
<p><strong>Agence Doorway</strong> — Coins Québec · %s.</p>
<ol>
<li><strong>Objet et durée.</strong> Cette entente régit l'inscription du partenaire
sur Coins Québec (fiche et visibilité). Sans durée minimale :
l'inscription reste active jusqu'à résiliation (clause 6). Reconduction tacite
mois après mois.</li>
<li><strong>Services inclus, sans frais fixes.</strong> Fiche partenaire (description,
offres, photos fournies par le partenaire) ; visibilité sur la carte Coins Québec ;
éligibilité au Carnet du Voyageur. Aucun abonnement fixe — voir la commission
(clause 3). Le shooting photo/vidéo n'est pas inclus.</li>
<li><strong>Commission.</strong> Réservation, visite ou consommation générée via
Coins Québec : <strong>%s&nbsp;%%</strong> seulement sur ce qui est réellement
apporté. Aucun frais fixe. Aucun frais un mois sans apport Coins Québec.</li>
<li><strong>Facturation.</strong> Commission calculée sur la réservation ou
consommation confirmée (hors annulations remboursées selon la politique du
partenaire). Devis et facture en dollars canadiens (CAD), taxes TPS et TVQ
applicables. Paiement par <strong>virement Interac</strong> à
<strong>comptabilite@agencedoorway.com</strong> (Agence Doorway).
Terminal IntelliX si le partenaire y souscrit. Pas de RIB marocain ni de dirhams.
Retard : délai de grâce de 7 à 15 jours avant suspension de la visibilité de
la fiche.</li>
<li><strong>Contenu photo/vidéo.</strong> Non inclus dans cette entente. Un
shooting ou une production avec l'Agence Doorway peut être convenu à part
(volet marketing, optionnel). Les photos fournies par le partenaire pour la
fiche restent sa propriété ; Coins Québec a un droit d'usage pour la promotion
(clause 8).</li>
<li><strong>Résiliation.</strong> Préavis 30 jours. La fiche est retirée.
Coins Québec peut suspendre ou résilier en cas de non-paiement, manquement
grave ou fraude.</li>
<li><strong>Niveau de service.</strong> Support partenaire : réponse sous
24–48 h ouvrées.</li>
<li><strong>Propriété intellectuelle.</strong> Photos/vidéos fournies par le
partenaire : sa propriété, licence d'usage Coins Québec (fiche, réseaux).
Marque Coins Québec : Agence Doorway.</li>
<li><strong>Données.</strong> Voyageurs et clients : Loi sur la protection des
renseignements personnels dans le secteur privé (Québec) et Loi 25.
Le partenaire n'utilise pas les coordonnées hors de la visite ou du séjour
réservé.</li>
<li><strong>Responsabilité.</strong> Coins Québec est un intermédiaire
technologique. La prestation (restauration, soin, activité) reste celle du
partenaire. Plafond : commissions perçues sur 12 mois, sauf faute lourde ou
intentionnelle.</li>
<li><strong>Force majeure.</strong> Suspension si événement hors contrôle
raisonnable.</li>
<li><strong>Révision.</strong> La commission (clause 3) peut être révisée avec
préavis écrit de 30 jours.</li>
<li><strong>Droit applicable.</strong> Droit du Québec et du Canada, tribunaux
compétents du district de Montréal (siège Agence Doorway).</li>
<li><strong>Divers.</strong> Cette entente constitue l'accord complet pour
cette catégorie. Cession interdite sans accord écrit. Notifications par
courriel ou WhatsApp officiel de la fiche.</li>
</ol>
""" % (
        categorie,
        pct,
    )
