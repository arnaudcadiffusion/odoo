from odoo.tests import TransactionCase, tagged

from odoo.addons.cadiffusion_base import (
    _quarantine_studio_debris,
    _restore_studio_debris,
    _studio_debris,
    _studio_debris_status,
)
from odoo.addons.cadiffusion_base.studio_debris import _quarantine_name


@tagged('post_install', '-at_install')
class TestStudioDebris(TransactionCase):
    """Garde-fous de l'inventaire et de la quarantaine des séquelles v15.

    L'inventaire tourne sur la base de test réelle : ce qu'il désigne sera un
    jour supprimé pour de bon, donc ce qu'on vérifie ici, c'est surtout ce
    qu'il ne doit JAMAIS désigner.
    """

    def test_inventory_is_read_only(self):
        """L'inventaire ne modifie rien — ni champs, ni tables."""
        cr = self.env.cr
        cr.execute('SELECT count(*) FROM ir_model_fields')
        fields_before = cr.fetchone()[0]
        cr.execute("""SELECT count(*) FROM information_schema.tables
                       WHERE table_schema = 'public'""")
        tables_before = cr.fetchone()[0]

        debris = _studio_debris(cr)
        self.assertEqual(set(debris),
                         {'ghost_fields', 'orphan_columns', 'dead_tables'})

        cr.execute('SELECT count(*) FROM ir_model_fields')
        self.assertEqual(cr.fetchone()[0], fields_before)
        cr.execute("""SELECT count(*) FROM information_schema.tables
                       WHERE table_schema = 'public'""")
        self.assertEqual(cr.fetchone()[0], tables_before)

    def test_live_fields_are_never_flagged(self):
        """Aucun champ vivant ne peut être pris pour un fantôme.

        C'est le garde-fou qui compte : un faux positif ici supprimerait la
        métadonnée d'un champ que le code déclare vraiment.
        """
        registry_fields = {
            (model_name, name)
            for model_name, model in self.env.registry.items()
            for name in model._fields
        }
        for ghost in _studio_debris(self.env.cr)['ghost_fields']:
            self.assertNotIn(
                (ghost['model'], ghost['name']), registry_fields,
                '%s.%s est déclaré dans le registre : ce n\'est pas un fantôme'
                % (ghost['model'], ghost['name']))

    def test_orphan_columns_have_no_field(self):
        """Une colonne signalée orpheline n'est exposée par aucun champ."""
        for orphan in _studio_debris(self.env.cr)['orphan_columns']:
            model = self.env.registry.get(orphan['model'])
            if model is None:
                continue
            self.assertNotIn(
                orphan['column'], model._fields,
                '%s.%s existe dans le registre' % (orphan['model'], orphan['column']))

    def test_dead_tables_have_no_model(self):
        """Une table signalée morte n'est celle d'aucun modèle enregistré."""
        live = {model.replace('.', '_') for model in self.env.registry}
        for dead in _studio_debris(self.env.cr)['dead_tables']:
            self.assertNotIn(dead['table'], live)

    def test_nothing_happens_without_a_category(self):
        """Sans catégorie explicite, la quarantaine est un no-op."""
        self.assertIsNone(_quarantine_studio_debris(self.env.cr))
        self.assertFalse(_studio_debris_status(self.env.cr)['quarantined'])

    def test_ghost_quarantine_round_trip(self):
        """Écarter puis restaurer les champs fantômes rend la base à l'identique.

        Seule catégorie exercée en test : elle ne fait que du DML. Écarter les
        tables mortes prendrait un verrou exclusif sur des tables de 300 000
        lignes, ce qui n'a pas sa place dans une suite de tests.
        """
        cr = self.env.cr
        ghosts = _studio_debris(cr)['ghost_fields']
        if not ghosts:
            self.skipTest('aucun champ fantôme sur cette base')
        cr.execute('SELECT count(*) FROM ir_model_fields')
        before = cr.fetchone()[0]

        batch = _quarantine_studio_debris(cr, ghost_fields=True)
        self.assertTrue(batch)
        self.assertEqual(_studio_debris(cr)['ghost_fields'], [])
        cr.execute('SELECT count(*) FROM ir_model_fields')
        self.assertEqual(cr.fetchone()[0], before - len(ghosts))

        _restore_studio_debris(cr, batch)
        cr.execute('SELECT count(*) FROM ir_model_fields')
        self.assertEqual(cr.fetchone()[0], before)
        self.assertEqual(
            {(ghost['model'], ghost['name'])
             for ghost in _studio_debris(cr)['ghost_fields']},
            {(ghost['model'], ghost['name']) for ghost in ghosts})
        self.assertFalse(_studio_debris_status(cr)['quarantined'])

    def test_quarantine_name_refuses_truncation(self):
        """Un identifiant que PostgreSQL tronquerait est refusé, pas tronqué —
        un nom tronqué serait introuvable à la restauration."""
        self.assertEqual(_quarantine_name('sale_order'), 'zz_dead_sale_order')
        with self.assertRaises(ValueError):
            _quarantine_name('x' * 60)
