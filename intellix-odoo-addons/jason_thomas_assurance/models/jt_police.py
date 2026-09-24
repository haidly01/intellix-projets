import re
from datetime import date, timedelta

from odoo import api, fields, models


class JTPolice(models.Model):
    _name = 'jt.police'
    _description = 'Police assurance vie JT'
    _inherit = ['mail.thread']
    _order = 'policy_number desc'
    _rec_name = 'policy_number'

    client_id = fields.Many2one('jt.client', string='Client', required=True, ondelete='cascade', index=True)
    policy_number = fields.Char('Numéro de police', required=True, index=True)
    policy_status = fields.Selection([
        ('en_force', 'En force'),
        ('en_traitement', 'En traitement'),
        ('accepte', 'Accepté'),
        ('refuse', 'Refusé'),
        ('echu', 'Échu'),
        ('autre', 'Autre'),
    ], string='Statut', default='en_force', tracking=True)
    product = fields.Char('Produit')
    product_code = fields.Char('Code produit')
    institution = fields.Selection([
        ('assomption_vie', 'Assomption Vie'),
        ('ago', 'Assure & Go'),
        ('inalco', 'Inalco'),
        ('ia_groupe', 'iA Groupe Financier'),
    ], string='Institution')
    submission_date = fields.Date('Date soumission')
    eff_date = fields.Date("Date d'entrée en vigueur")
    term_date = fields.Date("Date d'échéance")
    face_amount = fields.Float(
        'Montant ($)',
        digits=(16, 2),
        help='Capital assuré (vie) ou montant de couverture / indemnité max (Accis, maladie grave).',
    )
    premium = fields.Float('Prime ($)', digits=(16, 2))
    underwriting_status = fields.Char('Statut souscription')
    contract_type = fields.Char('Type contrat')
    source = fields.Selection([
        ('ago', 'AGO'),
        ('inalco', 'Inalco'),
        ('assomption_vie', 'Assomption Vie'),
    ], string='Source import')
    agent_code = fields.Char('Code agent')
    courtier = fields.Char('Courtier')
    coverage_number = fields.Char('Numéro couverture')
    annual_premium = fields.Float('Prime annuelle ($)', digits=(16, 2))
    product_family = fields.Selection([
        ('vie', 'Assurance vie'),
        ('accident_accis', 'Accident / Accis'),
        ('maladie_grave', 'Maladie grave'),
        ('autre', 'Autre'),
    ], string='Type de produit', compute='_compute_product_family', store=True, index=True)
    amount_label = fields.Char(
        'Libellé montant',
        compute='_compute_product_family',
        store=True,
        help='Capital assuré vs montant de couverture selon le type de produit.',
    )
    premium_label = fields.Char(
        'Libellé prime',
        compute='_compute_product_family',
        store=True,
        help='Mensuelle pour Accis / maladie grave AGO ; annuelle pour vie Assomption.',
    )
    coverage_summary = fields.Text(
        'Détail des couvertures',
        help='Pour Accis / maladie grave : unités et protections (quand dispo via sync AGO).',
    )
    payment_mode = fields.Char(
        'Mode de paiement',
        compute='_compute_payment_mode',
        store=True,
        help='Déduit du produit (ex. Payable 20 ans, Payable à vie, Nivelée).',
    )
    insured_names = fields.Char('Noms des assurés')
    owner_name = fields.Char('Propriétaire')
    payer_name = fields.Char('Payeur')
    owner_address = fields.Text('Adresse propriétaire')
    payer_address = fields.Text('Adresse payeur')
    address_group = fields.Char(
        'Adresse (groupe)',
        compute='_compute_address_group',
        store=True,
        index=True,
        help='Adresse normalisée pour regrouper les polices du même domicile.',
    )
    co_owner_name = fields.Char('Co-propriétaire')
    assomption_account = fields.Selection([
        ('6tz2', 'Compte 6TZ2 — Jason Thomas'),
        ('a0yx', 'Compte A0YX — Jason Thomas Assurance Inc'),
    ], string='Compte Assomption Vie')
    renew_within_30_days = fields.Boolean(
        'Renouvellement 30j', compute='_compute_renew_within_30_days', search='_search_renew_within_30_days',
    )
    transaction_ids = fields.One2many('jt.transaction', 'police_id', string='Transactions')
    activite_ids = fields.One2many('jt.activite', 'police_id', string='Activités')

    @staticmethod
    def _normalize_address(text):
        if not text:
            return False
        normalized = re.sub(r'[\r\n]+', ' ', str(text))
        normalized = re.sub(r'\s+', ' ', normalized).strip().upper()
        return normalized or False

    @api.depends('owner_address', 'payer_address')
    def _compute_address_group(self):
        for record in self:
            record.address_group = (
                self._normalize_address(record.owner_address)
                or self._normalize_address(record.payer_address)
            )

    @api.depends('product', 'contract_type', 'product_code')
    def _compute_product_family(self):
        for record in self:
            raw = f'{record.product or ""} {record.contract_type or ""} {record.product_code or ""}'.upper()
            family = 'autre'
            label = 'Montant ($)'
            prem_label = 'Prime annuelle ($)'
            if re.search(r'\bACCI|ACCIS|FRACTURE|ACCIDENT', raw):
                family = 'accident_accis'
                label = 'Montant de couverture ($)'
                prem_label = 'Prime mensuelle ($)'
            elif re.search(r'CANCER|MALADIE\s*GRAVE|CRITICAL|PROGRAMME\s+SUP', raw):
                family = 'maladie_grave'
                label = 'Montant de couverture ($)'
                prem_label = 'Prime mensuelle ($)'
            elif re.search(
                r'\bVIE\b|PARPLUS|FLEXTERM|PLATINE|UNIVERSEL|TEMPORAIRE|'
                r'PROTECTION\s+OR|ACC[EÈ]S\s+VIE|PAYABLE\s+\d+\s*ANS',
                raw,
            ):
                family = 'vie'
                label = 'Capital assuré ($)'
                prem_label = 'Prime annuelle ($)'
            record.product_family = family
            record.amount_label = label
            record.premium_label = prem_label

    @api.depends('product', 'contract_type')
    def _compute_payment_mode(self):
        for record in self:
            raw = f'{record.product or ""} {record.contract_type or ""}'.upper()
            mode = False
            m = re.search(r'PAYABLE\s+(À|A)\s+VIE', raw)
            if m:
                mode = 'Payable à vie'
            else:
                m = re.search(r'PAYABLE\s+(\d+)\s*ANS?', raw)
                if m:
                    mode = f'Payable {m.group(1)} ans'
                elif 'NIVEL' in raw:
                    mode = 'Prime nivelée'
                elif re.search(r'\bACCI|ACCIS', raw):
                    mode = 'Mensuel'
                elif re.search(r'CANCER|MALADIE\s*GRAVE|PROGRAMME\s+SUP', raw):
                    mode = 'Mensuel'
                elif 'TEMPORAIRE' in raw or 'TERM' in raw:
                    mode = 'Temporaire / term'
                elif 'VIE ENTI' in raw:
                    mode = 'Vie entière'
            record.payment_mode = mode

    @api.depends('term_date')
    def _compute_renew_within_30_days(self):
        today = date.today()
        limit = today + timedelta(days=30)
        for record in self:
            record.renew_within_30_days = bool(
                record.term_date and today <= record.term_date <= limit
            )

    def _search_renew_within_30_days(self, operator, value):
        today = date.today()
        limit = today + timedelta(days=30)
        in_range = [('term_date', '>=', today), ('term_date', '<=', limit)]
        if (operator == '=' and value) or (operator == '!=' and not value):
            return in_range
        return ['|', ('term_date', '=', False), '|', ('term_date', '<', today), ('term_date', '>', limit)]
