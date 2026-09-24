import csv
import importlib.util
import os
import re

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open

from odoo.addons.cadiffusion_base import _load_field_rename_map
from odoo.addons.cadiffusion_base.field_rename import (
    NEW_PREFIX,
    OLD_PREFIX,
    _ensure_journal,
    _rename_fields_in_text,
    _rename_helpers_in_text,
    _restore_text_rows,
    _rewrite_column,
)
from odoo.addons.cadiffusion_base.studio_debris import _load_retire_map


def _load_builder():
    """Loads data/build_field_rename_map.py, which is not an importable
    Python module (data/ is not a package) but knows how to read the fields
    declared in the sources."""
    path = os.path.join(get_module_path('cadiffusion_base'), 'data',
                        'build_field_rename_map.py')
    spec = importlib.util.spec_from_file_location('build_field_rename_map', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decisions():
    with file_open('cadiffusion_base/data/field_decisions.csv', 'r') as handle:
        return {row['old_name']: row for row in csv.DictReader(handle)}


@tagged('post_install', '-at_install')
class TestFieldRename(TransactionCase):
    """Guards of the x_studio_* -> cad_* rename: the mapping table, the
    customer's decisions and the reversibility of the text substitutions."""

    def test_map_matches_sources(self):
        """The CSV follows the fields actually declared in addons_project,
        and no x_studio_ field is declared any more.

        The only guard against drift: a field added or renamed after the
        generation of the CSV would be left behind by the rollback.
        """
        builder = _load_builder()
        self.assertEqual(
            builder.declared_fields(OLD_PREFIX), [],
            'x_studio_ fields are still declared in the sources')
        declared = {(row['model'], row['name'])
                    for row in builder.declared_fields(NEW_PREFIX)}
        mapped = {(model, new) for model, _old, new, _ttype
                  in _load_field_rename_map()}
        self.assertEqual(mapped, declared,
                         'data/field_rename_map.csv drifted from the sources')

    def test_map_follows_decisions(self):
        """Every row of the map applies a "keep" decision with its exact
        target name, every retired field a "delete" one."""
        decisions = _decisions()
        for _model, old, new, _ttype in _load_field_rename_map():
            self.assertEqual(decisions[old]['decision'], 'keep', old)
            self.assertEqual(decisions[old]['new_name'], new, old)
        for _model, name in _load_retire_map():
            self.assertEqual(decisions[name]['decision'], 'delete', name)

    def test_retired_fields_are_gone(self):
        """No retired field is left in the registry."""
        for model, name in _load_retire_map():
            if model in self.env:
                self.assertNotIn(name, self.env[model]._fields,
                                 '%s.%s is retired' % (model, name))

    def test_map_is_consistent(self):
        """One new name per old name, unique per model, and valid
        identifiers. Two old names may converge on different models."""
        entries = _load_field_rename_map()
        self.assertTrue(entries, 'empty mapping table')
        targets, forward = {}, {}
        for model, old, new, _ttype in entries:
            self.assertTrue(old.startswith(OLD_PREFIX), old)
            self.assertTrue(new.startswith(NEW_PREFIX), new)
            self.assertTrue(new.isidentifier() and new.isascii(), new)
            self.assertEqual(forward.setdefault(old, new), new, old)
            self.assertNotIn((model, new), targets,
                             'collision on %s.%s' % (model, new))
            targets[(model, new)] = old

    def test_new_names_are_free(self):
        """None of the new names is already taken on its model while the old
        one is still there - the rename would overwrite a field."""
        fields = self.env['ir.model.fields'].sudo()
        for model, old, new, _ttype in _load_field_rename_map():
            if (fields.search_count([('model', '=', model), ('name', '=', new)])
                    and fields.search_count([('model', '=', model),
                                             ('name', '=', old)])):
                self.fail('%s.%s already exists while %s is still there'
                          % (model, new, old))

    def test_substitution_is_reversible(self):
        """Round trip on the forms actually met: domain, view arch, dotted
        path, method name."""
        samples = [
            "[('x_studio_transport', '=', 'DPD')]",
            '<field name="x_studio_nb_palette" invisible="not x_studio_bl_groupe"/>',
            "{'search_default_x_studio_transport': 1}",
            "{'default_x_studio_bl_groupe': True}",
            "related='partner_id.x_studio_notes_internes'",
            "compute='_compute_x_studio_prix_remise'",
            "def _compute_x_studio_prix_remise(self):",
        ]
        for sample in samples:
            forward = _rename_helpers_in_text(_rename_fields_in_text(sample))
            self.assertNotIn(OLD_PREFIX, forward, sample)
            back = _rename_helpers_in_text(
                _rename_fields_in_text(forward, reverse=True), reverse=True)
            self.assertEqual(back, sample)

    def test_names_follow_the_decisions(self):
        """Names are not mechanical: they come from the spreadsheet."""
        self.assertEqual(_rename_fields_in_text('x_studio_prparateur'),
                         'cad_preparateur')
        self.assertEqual(_rename_fields_in_text('x_studio_assurance'),
                         'cad_credit_safe')
        self.assertEqual(_rename_fields_in_text('x_studio_pod_1'), 'cad_pol_1')

    def test_converging_names_are_not_reversed(self):
        """cad_assurance comes from two old names: the reverse substitution
        leaves it alone rather than guessing."""
        self.assertEqual(_rename_fields_in_text('x_studio_atradius'),
                         'cad_assurance')
        self.assertEqual(_rename_fields_in_text('x_studio_assurance_bc'),
                         'cad_assurance')
        self.assertEqual(
            _rename_fields_in_text('cad_assurance', reverse=True), 'cad_assurance')

    def test_substitution_respects_word_boundaries(self):
        """A name prefixing another one must not be cut in two."""
        text = 'x_studio_transport x_studio_transport_po x_studio_transport_achat'
        renamed = _rename_fields_in_text(text)
        self.assertEqual(renamed,
                         'cad_transport cad_transport_po cad_transport_achat')
        self.assertFalse(re.search(r'\bcad_transport_po_', renamed))
        self.assertEqual(_rename_fields_in_text(renamed, reverse=True), text)

    def test_context_keys_are_renamed(self):
        self.assertEqual(
            _rename_fields_in_text("{'search_default_x_studio_transport': 1}"),
            "{'search_default_cad_transport': 1}")

    def test_unknown_and_retired_names_are_left_alone(self):
        """Nothing outside the mapping table is touched - retired fields
        included: their name in the database must stay what it is."""
        text = 'x_studio_champ_inconnu x_studio_marge x_studio_notes_interne'
        self.assertEqual(_rename_fields_in_text(text), text)

    def test_text_rows_restored_from_journal(self):
        """The rollback puts back the exact text, converging names included,
        and does not overwrite a row edited since the rename."""
        cr = self.env.cr
        domain = "[('x_studio_atradius', '=', 'ACCEPTEE')]"
        edited = "[('x_studio_assurance_bc', '=', 'PUBLIC')]"
        # Raw SQL: the domains name fields that no longer exist.
        ids = []
        for model, value in (('res.partner', domain), ('sale.order', edited)):
            cr.execute("""INSERT INTO ir_filters
                              (name, model_id, domain, context, sort, active)
                          VALUES ('TEST RENAME', %s, %s, '{}', '[]', true)
                       RETURNING id""",
                       (model, value))
            ids.append(cr.fetchone()[0])

        def current(filter_id):
            cr.execute('SELECT domain FROM ir_filters WHERE id = %s', (filter_id,))
            return cr.fetchone()[0]

        _ensure_journal(cr)
        batch = '999999'
        _rewrite_column(cr, 'ir_filters', 'domain', False,
                        only={'x_studio_atradius', 'x_studio_assurance_bc'},
                        batch=batch)
        self.assertEqual(current(ids[0]), "[('cad_assurance', '=', 'ACCEPTEE')]")
        cr.execute('UPDATE ir_filters SET domain = %s WHERE id = %s',
                   ("[('cad_assurance', '=', 'INTERNE')]", ids[1]))

        _restore_text_rows(cr, batch)
        self.assertEqual(current(ids[0]), domain)
        # Edited since: kept as edited, the converging name is not guessed.
        self.assertEqual(current(ids[1]), "[('cad_assurance', '=', 'INTERNE')]")
