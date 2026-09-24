from odoo import models, fields

class LeadCampaignMap(models.Model):
    _name = 'lead.campaign.map'
    _description = 'Country to Campaign Mapping'

    # Relation vers le pays (Many2one)
    country_id = fields.Many2one('res.country', string="Country", required=True)
    
    # Nom du tag (ex: insurance, iptv)
    tag_name = fields.Char(string="Tag") 
    
    # Nom de la campagne à appliquer
    campaign_name = fields.Char(string="Campaign Name", required=True)