from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    picking_label_print_server_url = fields.Char(
        config_parameter='cadiffusion_picking_label_print.picking_label_print_server_url')
    picking_transpot_server_url = fields.Char(
        config_parameter='cadiffusion_picking_label_print.picking_transpot_server_url')
