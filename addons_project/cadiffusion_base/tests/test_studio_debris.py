from odoo.tests import TransactionCase, tagged

from odoo.addons.cadiffusion_base import (
    _quarantine_studio_debris,
    _restore_studio_debris,
    _studio_debris,
    _studio_debris_status,
)
from odoo.addons.cadiffusion_base.studio_debris import (
    _column_exists,
    _quarantine_name,
    _retire_fields,
)


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
        """Sans catégorie explicite, la quarantaine est un no-op.

        On compare l'état avant/après plutôt que d'exiger l'absence de
        quarantaine : la base peut légitimement en porter une déjà appliquée.
        """
        before = _studio_debris_status(self.env.cr)
        self.assertIsNone(_quarantine_studio_debris(self.env.cr))
        self.assertEqual(_studio_debris_status(self.env.cr), before)

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
        # La base peut déjà porter une quarantaine appliquée : on repart de son
        # état, pas de l'hypothèse qu'il n'y en a aucune.
        status_before = _studio_debris_status(cr)

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
        self.assertEqual(_studio_debris_status(cr), status_before)

    def test_retire_round_trip(self):
        """Retiring a field sets its column aside, detaches its xmlid (so the
        end of the upgrade does not DROP it) and archives the filters naming
        it; restoring puts everything back, data included.

        Played on a dummy column of the small ca_diffusion_preparer table.
        """
        cr = self.env.cr
        name = 'x_studio_test_retire'
        cr.execute('ALTER TABLE ca_diffusion_preparer ADD COLUMN %s varchar' % name)
        cr.execute("UPDATE ca_diffusion_preparer SET %s = 'kept'" % name)
        cr.execute('SELECT count(*) FROM ca_diffusion_preparer')
        rows = cr.fetchone()[0]
        cr.execute("""INSERT INTO ir_model_fields
                          (model, model_id, name, field_description, ttype,
                           state, store)
                      SELECT 'ca.diffusion.preparer', id, %s, '{"en_US": "Test"}',
                             'char', 'base', true
                        FROM ir_model WHERE model = 'ca.diffusion.preparer'
                   RETURNING id""", (name,))
        field_id = cr.fetchone()[0]
        cr.execute("""INSERT INTO ir_model_data (module, name, model, res_id)
                      VALUES ('cadiffusion_base', %s, 'ir.model.fields', %s)""",
                   ('field_ca_diffusion_preparer__' + name, field_id))
        cr.execute("""INSERT INTO ir_filters
                          (name, model_id, domain, context, sort, active)
                      VALUES ('TEST RETIRE', 'ca.diffusion.preparer', %s, '{}',
                              '[]', true) RETURNING id""",
                   ("[('%s', '!=', False)]" % name,))
        filter_id = cr.fetchone()[0]

        def xmlids():
            cr.execute("""SELECT count(*) FROM ir_model_data
                           WHERE model = 'ir.model.fields' AND res_id = %s""",
                       (field_id,))
            return cr.fetchone()[0]

        def filter_active():
            cr.execute('SELECT active FROM ir_filters WHERE id = %s', (filter_id,))
            return cr.fetchone()[0]

        batch = _retire_fields(cr, [('ca.diffusion.preparer', name)])
        self.assertTrue(batch)
        self.assertFalse(_column_exists(cr, 'ca_diffusion_preparer', name))
        self.assertTrue(_column_exists(cr, 'ca_diffusion_preparer',
                                       _quarantine_name(name)))
        self.assertEqual(xmlids(), 0)
        self.assertFalse(filter_active())
        cr.execute('SELECT 1 FROM ir_model_fields WHERE id = %s', (field_id,))
        self.assertTrue(cr.fetchone(), 'the field row must stay')
        self.assertIsNone(_retire_fields(cr, [('ca.diffusion.preparer', name)]),
                          'a second pass has nothing left to do')

        _restore_studio_debris(cr, batch)
        cr.execute("SELECT count(*) FROM ca_diffusion_preparer WHERE %s = 'kept'"
                   % name)
        self.assertEqual(cr.fetchone()[0], rows)
        self.assertEqual(xmlids(), 1)
        self.assertTrue(filter_active())

    def test_quarantine_name_refuses_truncation(self):
        """Un identifiant que PostgreSQL tronquerait est refusé, pas tronqué —
        un nom tronqué serait introuvable à la restauration."""
        self.assertEqual(_quarantine_name('sale_order'), 'zz_dead_sale_order')
        with self.assertRaises(ValueError):
            _quarantine_name('x' * 60)
