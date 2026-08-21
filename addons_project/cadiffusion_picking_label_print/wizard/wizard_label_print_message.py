from odoo import fields, models

class WizardLabelPrintMessage(models.TransientModel):
    _name = 'wizard.label.print.message'
    _description = "Message d'impression des étiquettes colis"

    message = fields.Text(string='Message', required=True)
