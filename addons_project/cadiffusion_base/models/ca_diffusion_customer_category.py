from odoo import _, api, models
from odoo.exceptions import ValidationError


class CaDiffusionCustomerCategory(models.Model):
    """Configurable list backing res.partner.cad_categorie_client (and its
    related copy on sale.order), so that the customer can add or rename a
    category without a code change.

    Same guarantees as the preparer lists it derives from (prototype
    inheritance of ca.diffusion.preparer): a name still carried by a partner
    cannot be deleted, a rename is propagated to the partners, an archived
    name stays proposed as long as it is in use.
    """

    _name = 'ca.diffusion.customer.category'
    _inherit = 'ca.diffusion.preparer'
    _description = 'Customer category (configurable list)'

    _LIST_FIELDS = {
        'customer_category': [('res.partner', 'cad_categorie_client')],
    }

    # Former hardcoded list, to seed a database with empty columns.
    _SEED_VALUES = {
        'customer_category': [
            'AUTRE',
            'DISTRIBUTEUR AGRO - INDUS - HYG',
            'DISTRIBUTEUR MEDICAL',
            'DIVERS AGRO - INDUS - HYG',
            'DIVERS MEDICAL',
            'EHPAD',
            'FOURNISSEUR',
            'HOPITAL PRIVE - CLINIQUE',
            'HOPITAL PUBLIC',
            'INTERNE',
            'MAIRIE - COLLECTIVITE - CRECHE',
            'SDIS',
            'VAD',
        ],
    }

    @api.model
    def _selection_list_type(self):
        return [('customer_category', 'Customer categories')]

    @api.model
    def _check_field_values(self, records, field_name, list_type):
        allowed = set(self.sudo()._proposable_names(list_type))
        for record in records:
            value = record[field_name]
            if value and value not in allowed:
                raise ValidationError(_(
                    "\"%(value)s\" is not part of the customer categories. "
                    "Add it first in Sales → Configuration → Customer "
                    "Categories.",
                    value=value))
