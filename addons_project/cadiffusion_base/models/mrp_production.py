from odoo import api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    x_studio_conditionnement = fields.Char(
        string='Conditionnement',
        compute='_compute_x_studio_conditionnement',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('product_id')
    def _compute_x_studio_conditionnement(self):
        for production in self:
            packaging = production.product_id.product_tmpl_id.uom_ids[:1]
            production.x_studio_conditionnement = packaging.name if packaging else False

    x_studio_impression_mo = fields.Boolean(
        string='Impression MO',
        default=False,
    )
    x_studio_notes = fields.Text(
        string='Notes',
    )
    x_studio_preparateur_kit = fields.Selection(
        selection=[
            ('SABINE', 'SABINE'),
            ('ZAHIA', 'ZAHIA'),
            ('CYRIL', 'CYRIL'),
            ('MANUEL', 'MANUEL'),
            ('AUTRE', 'AUTRE'),
        ],
        string='Preparateur_Kit',
    )

    def action_open_project(self):
        return True
