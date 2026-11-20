from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCustomerCategories(TransactionCase):
    """Configurable customer categories (res.partner.cad_categorie_client):
    every stored value must belong to the list, otherwise blank tab."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env['ca.diffusion.customer.category']
        cls.Category._seed_lists()
        cls.partner = cls.env['res.partner'].create({'name': 'TEST CATEGORIE'})

    def _selection_keys(self, model_name, field_name):
        description = self.env[model_name].fields_get([field_name])
        return [key for key, _label in description[field_name]['selection']]

    def test_seed_provides_historical_values(self):
        keys = self._selection_keys('res.partner', 'cad_categorie_client')
        for name in ('AUTRE', 'EHPAD', 'HOPITAL PUBLIC', 'VAD'):
            self.assertIn(name, keys)

    def test_seed_covers_stored_values(self):
        keys = {key for key, _label
                in self.Category._selection_for('customer_category')}
        self.env.cr.execute("""SELECT DISTINCT cad_categorie_client FROM res_partner
                                WHERE cad_categorie_client IS NOT NULL""")
        orphans = {value for (value,) in self.env.cr.fetchall()} - keys
        self.assertFalse(orphans, 'Stored values outside the list: %s'
                         % sorted(orphans))

    def test_lists_are_separate_from_preparers(self):
        self.Category.create({'name': 'TEST CATEGORIE SEULE'})
        self.assertNotIn(
            'TEST CATEGORIE SEULE',
            self._selection_keys('stock.picking', 'cad_preparateur'))
        self.assertFalse(self.env['ca.diffusion.preparer'].search(
            [('name', '=', 'TEST CATEGORIE SEULE')]))

    def test_new_entry_selectable_on_partner_and_order(self):
        self.Category.create({'name': ' TEST NOUVELLE '})
        self.assertIn('TEST NOUVELLE',
                      self._selection_keys('res.partner', 'cad_categorie_client'))
        self.assertIn('TEST NOUVELLE',
                      self._selection_keys('sale.order', 'cad_categorie_client'))
        self.partner.cad_categorie_client = 'TEST NOUVELLE'
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.assertEqual(order.cad_categorie_client, 'TEST NOUVELLE')

    def test_unknown_value_rejected(self):
        with self.assertRaises(ValidationError):
            self.partner.cad_categorie_client = 'TEST INCONNUE'
            self.partner.flush_recordset()

    def test_rename_propagates(self):
        entry = self.Category.create({'name': 'TEST AVANT'})
        self.partner.cad_categorie_client = 'TEST AVANT'
        entry.name = 'TEST APRES'
        self.partner.invalidate_recordset(['cad_categorie_client'])
        self.assertEqual(self.partner.cad_categorie_client, 'TEST APRES')

    def test_used_entry_cannot_be_deleted(self):
        entry = self.Category.create({'name': 'TEST UTILISEE'})
        self.partner.cad_categorie_client = 'TEST UTILISEE'
        with self.assertRaises(UserError):
            entry.unlink()
        self.partner.cad_categorie_client = False
        entry.unlink()
