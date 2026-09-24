from odoo import fields, http
from odoo.http import request


class JTClientPortal(http.Controller):

    def _get_access(self, token):
        return request.env['jt.portal.access'].sudo().search([
            ('token', '=', token),
            ('is_active', '=', True),
        ], limit=1)

    @http.route('/portail/erreur', type='http', auth='public', website=True)
    def portal_error_page(self, **kwargs):
        return request.render('jt_client_portal.portal_error', {
            'message': kwargs.get('message', 'Lien invalide ou expiré.'),
        })

    @http.route('/portail/<string:token>', type='http', auth='public', website=True)
    def portal_home(self, token, **kwargs):
        access = self._get_access(token)
        if not access:
            return request.render('jt_client_portal.portal_error', {
                'message': 'Lien invalide ou expiré.',
            })
        access.sudo().write({'last_login': fields.Datetime.now()})
        client = access.client_id
        polices_en_force = client.police_ids.filtered(lambda p: p.policy_status == 'en_force')
        return request.render('jt_client_portal.portal_home', {
            'client': client,
            'token': token,
            'polices_en_force': polices_en_force,
            'total_capital': sum(polices_en_force.mapped('face_amount')),
            'nb_polices': len(polices_en_force),
        })

    @http.route('/portail/<string:token>/polices', type='http', auth='public', website=True)
    def portal_polices(self, token, **kwargs):
        access = self._get_access(token)
        if not access:
            return request.redirect('/portail/erreur')
        client = access.client_id
        polices = client.police_ids.sorted('eff_date', reverse=True)
        return request.render('jt_client_portal.portal_polices', {
            'client': client,
            'token': token,
            'polices': polices,
        })

    @http.route('/portail/<string:token>/police/<int:police_id>', type='http', auth='public', website=True)
    def portal_police_detail(self, token, police_id, **kwargs):
        access = self._get_access(token)
        if not access:
            return request.redirect('/portail/erreur')
        police = request.env['jt.police'].sudo().browse(police_id)
        if not police.exists() or police.client_id.id != access.client_id.id:
            return request.redirect('/portail/erreur')
        transactions = police.transaction_ids.filtered(lambda t: t.pdf_url).sorted('event_date', reverse=True)
        return request.render('jt_client_portal.portal_police_detail', {
            'client': access.client_id,
            'token': token,
            'police': police,
            'transactions': transactions,
        })

    @http.route('/portail/<string:token>/contact', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def portal_contact(self, token, **kwargs):
        access = self._get_access(token)
        if not access:
            return request.redirect('/portail/erreur')
        if request.httprequest.method == 'POST':
            sujet = kwargs.get('sujet', '').strip()
            message = kwargs.get('message', '').strip()
            tag = request.env.ref('jt_client_portal.tag_portail_client', raise_if_not_found=False)
            lead_vals = {
                'name': f'[PORTAIL] {access.client_id.full_name} — {sujet or "Contact"}',
                'partner_name': access.client_id.full_name,
                'phone': access.client_id.cell_phone,
                'email_from': access.email,
                'description': message,
            }
            if tag:
                lead_vals['tag_ids'] = [(4, tag.id)]
            request.env['crm.lead'].sudo().create(lead_vals)
            return request.render('jt_client_portal.portal_contact_merci', {
                'client': access.client_id,
                'token': token,
            })
        return request.render('jt_client_portal.portal_contact', {
            'client': access.client_id,
            'token': token,
        })
