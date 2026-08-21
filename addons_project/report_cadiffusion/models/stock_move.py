# Copyright 2018 Shine IT
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models

class StockMove(models.Model):
    _inherit = 'stock.move'
    article_cmd = fields.Char('Article cmdé', related='sale_line_id.article_cmd',
                              related_sudo=True)
    note_text = fields.Text('Notes')
