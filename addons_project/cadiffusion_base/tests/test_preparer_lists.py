from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPreparerLists(TransactionCase):
    """Configurable preparer lists: every stored value must belong to
    the choices of its list (otherwise blank tab)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Preparateur = cls.env['ca.diffusion.preparer']
        cls.Preparateur._seed_lists()
        picking_type = (
            cls.env['stock.picking.type'].search(
                [('code', '=', 'internal')], limit=1)
            or cls.env['stock.picking.type'].search([], limit=1))
        cls.picking = cls.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
        })

    def _selection_keys(self, model_name, field_name):
        description = self.env[model_name].fields_get([field_name])
        return [key for key, _label in description[field_name]['selection']]

    def test_seed_covers_stored_values(self):
        for list_type, specs in self.Preparateur._LIST_FIELDS.items():
            keys = {key for key, _label
                    in self.Preparateur._selection_for(list_type)}
            for model_name, field_name in specs:
                self.env.cr.execute(
                    'SELECT DISTINCT "%s" FROM "%s" WHERE "%s" IS NOT NULL'
                    % (field_name, self.env[model_name]._table, field_name))
                stored = {value for (value,) in self.env.cr.fetchall()}
                orphans = stored - keys
                self.assertFalse(
                    orphans,
                    "Stored values outside the list on %s.%s: %s"
                    % (model_name, field_name, sorted(orphans)))

    def test_seed_provides_historical_values(self):
        keys = self._selection_keys('stock.picking', 'x_studio_prparateur')
        for name in ('CYRIL', 'DAVID', 'ANCIEN SALARIE'):
            self.assertIn(name, keys)
        self.assertIn(
            'AUTRE',
            self._selection_keys('mrp.production', 'x_studio_preparateur_kit'))

    def test_new_entry_becomes_selectable(self):
        self.Preparateur.create(
            {'name': ' TEST NOUVEAU ', 'list_type': 'transfer'})
        keys = self._selection_keys('stock.picking', 'x_studio_prparateur')
        self.assertIn('TEST NOUVEAU', keys)
        self.assertNotIn(' TEST NOUVEAU ', keys)
        self.picking.x_studio_prparateur = 'TEST NOUVEAU'
        self.assertEqual(self.picking.x_studio_prparateur, 'TEST NOUVEAU')

    def test_unknown_value_rejected(self):
        """Rejected by our constraint: the v19 ORM no longer validates
        dynamic Selections."""
        with self.assertRaises(ValidationError):
            self.picking.x_studio_prparateur = 'HORS LISTE'
            self.picking.flush_recordset(['x_studio_prparateur'])

    def test_rename_propagates_to_records(self):
        entry = self.Preparateur.create(
            {'name': 'TEST RENOMMAGE', 'list_type': 'transfer'})
        self.picking.x_studio_prparateur = 'TEST RENOMMAGE'
        entry.name = 'TEST RENOMME'
        self.assertEqual(self.picking.x_studio_prparateur, 'TEST RENOMME')
        keys = self._selection_keys('stock.picking', 'x_studio_prparateur')
        self.assertIn('TEST RENOMME', keys)
        self.assertNotIn('TEST RENOMMAGE', keys)

    def test_unlink_blocked_while_used(self):
        entry = self.Preparateur.create(
            {'name': 'TEST SUPPRESSION', 'list_type': 'transfer'})
        self.picking.x_studio_prparateur = 'TEST SUPPRESSION'
        with self.assertRaises(UserError):
            entry.unlink()
        self.picking.x_studio_prparateur = False
        entry.unlink()
        self.assertNotIn(
            'TEST SUPPRESSION',
            self._selection_keys('stock.picking', 'x_studio_prparateur'))

    def test_list_type_change_blocked_while_used(self):
        entry = self.Preparateur.create(
            {'name': 'TEST DEPLACEMENT', 'list_type': 'transfer'})
        self.picking.x_studio_prparateur = 'TEST DEPLACEMENT'
        with self.assertRaises(UserError):
            entry.list_type = 'kit'

    def test_archived_entry_hidden_only_when_unused(self):
        unused = self.Preparateur.create(
            {'name': 'TEST ARCHIVE LIBRE', 'list_type': 'transfer'})
        used = self.Preparateur.create(
            {'name': 'TEST ARCHIVE PORTE', 'list_type': 'transfer'})
        self.picking.x_studio_prparateur = 'TEST ARCHIVE PORTE'
        (unused + used).action_archive()
        keys = self._selection_keys('stock.picking', 'x_studio_prparateur')
        self.assertNotIn('TEST ARCHIVE LIBRE', keys)
        self.assertIn('TEST ARCHIVE PORTE', keys)

    def test_seed_recovers_legacy_value(self):
        """Value unknown to the code sleeping in the column (v15 drift):
        picked up by the seeding without touching the data."""
        self.picking.flush_recordset(['x_studio_prparateur'])
        self.env.cr.execute(
            "UPDATE stock_picking SET x_studio_prparateur = %s WHERE id = %s",
            ('TEST VALEUR HERITEE', self.picking.id))
        self.picking.invalidate_recordset(['x_studio_prparateur'])
        self.Preparateur._seed_lists()
        keys = self._selection_keys('stock.picking', 'x_studio_prparateur')
        self.assertIn('TEST VALEUR HERITEE', keys)
        self.assertEqual(
            self.picking.x_studio_prparateur, 'TEST VALEUR HERITEE')
        entry = self.Preparateur.search(
            [('name', '=', 'TEST VALEUR HERITEE'),
             ('list_type', '=', 'transfer')])
        self.assertTrue(entry.active)

    def test_duplicate_name_rejected(self):
        self.Preparateur.create(
            {'name': 'TEST DOUBLON', 'list_type': 'transfer'})
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.Preparateur.create(
                {'name': 'TEST DOUBLON', 'list_type': 'transfer'})
        self.Preparateur.create({'name': 'TEST DOUBLON', 'list_type': 'kit'})
