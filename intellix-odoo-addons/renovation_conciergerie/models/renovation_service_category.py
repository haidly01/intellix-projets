from odoo import fields, models

class RenovationServiceCategory(models.Model):
    _name = "renovation.service.category"
    _description = "Catégorie de service rénovation"
    _parent_name = "parent_id"
    _parent_store = True
    _parent_order = "sequence, name"
    _order = "parent_path, sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    description = fields.Html(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    parent_path = fields.Char(index=True, unaccent=False)
    parent_id = fields.Many2one(
        "renovation.service.category",
        string="Catégorie parente",
        index=True,
        ondelete="cascade",
    )
    child_ids = fields.One2many(
        "renovation.service.category",
        "parent_id",
        string="Sous-catégories",
    )
    package_ids = fields.Many2many(
        "renovation.partner.package",
        "renovation_package_category_rel",
        "category_id",
        "package_id",
        string="Forfaits",
    )
