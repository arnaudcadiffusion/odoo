from odoo import fields, models

class WizardLabelPrintMessage(models.TransientModel):
    _name = 'wizard.label.print.message'

    message = fields.Text(string='Message', required=True)
