from odoo import http
from odoo.http import request

class LeadAPI(http.Controller):

    @http.route('/api/leads', type='json', auth='public', methods=['POST'], csrf=False)
    def create_lead(self, **kwargs):
        # In type='json' routes, Odoo automatically parses the JSON body
        # and passes it into kwargs.
        data = kwargs
        lead_model = request.env['crm.lead'].sudo()
        lead_fields = lead_model._fields

        lead_values = {
            'name': data.get('name'),
            'email_from': data.get('email'),
            'phone': data.get('phone'),
            'description': data.get('thematique'), # Example mapping
        }

        if data.get('country_id'):
            lead_values['country_id'] = data.get('country_id')

        if 'x_thematique' in lead_fields:
            lead_values['x_thematique'] = data.get('thematique')

        lead = lead_model.create(lead_values)

        return {
            'status': 'success',
            'lead_id': lead.id,
            'assigned_thematique': data.get('thematique')
        }
