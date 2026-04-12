# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    x_studio_conditionnement = fields.Char(
        string='Conditionnement',
    )
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
