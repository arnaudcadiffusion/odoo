import importlib.util
import os
import re

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

from odoo.addons.cadiffusion_base import _load_field_rename_map
from odoo.addons.cadiffusion_base.field_rename import (
    NEW_PREFIX,
    OLD_PREFIX,
    _rename_fields_in_text,
    _rename_helpers_in_text,
)


def _load_builder():
    """Charge data/build_field_rename_map.py, qui n'est pas un module Python
    importable (data/ n'est pas un paquet) mais reste la source de vérité de
    ce que le CSV doit contenir."""
    path = os.path.join(get_module_path('cadiffusion_base'), 'data',
                        'build_field_rename_map.py')
    spec = importlib.util.spec_from_file_location('build_field_rename_map', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestFieldRename(TransactionCase):
    """Garde-fous de l'outillage de renommage x_studio_* → ca_diff_*.

    Le renommage n'est pas appliqué : ces tests verrouillent la table de
    correspondance et la réversibilité des substitutions, pour que l'aller ET
    le retour restent valides le jour où une migration les déclenche.
    """

    def test_map_matches_sources(self):
        """Le CSV suit les champs réellement déclarés dans addons_project.

        Ce test est le seul rempart contre la dérive : un champ x_studio_
        ajouté après la génération du CSV serait laissé derrière par le
        renommage, et un champ retiré ferait échouer le rollback.
        """
        declared = {(row['model'], row['old_name'], row['new_name'])
                    for row in _load_builder().collect()}
        if not declared:
            self.skipTest('renommage déjà appliqué : plus aucun champ x_studio_')
        mapped = {(model, old, new) for model, old, new, _ttype
                  in _load_field_rename_map()}
        self.assertEqual(
            mapped, declared,
            "data/field_rename_map.csv a dérivé des sources — relancer "
            "python3 data/build_field_rename_map.py")

    def test_map_is_bijective(self):
        """Deux anciens noms ne peuvent pas tomber sur le même nouveau nom, et
        les nouveaux noms sont des identifiants Python valides."""
        entries = _load_field_rename_map()
        self.assertTrue(entries, 'table de correspondance vide')
        forward = {}
        for model, old, new, _ttype in entries:
            self.assertTrue(old.startswith(OLD_PREFIX), old)
            self.assertTrue(new.startswith(NEW_PREFIX), new)
            self.assertRegex(new, r'^[a-z][a-z0-9_]*[A-Za-z0-9]$|^[a-z][a-z0-9_]*$')
            self.assertTrue(new.isidentifier(), new)
            self.assertNotIn((model, new), forward,
                             'collision sur %s.%s' % (model, new))
            forward[(model, new)] = old

    def test_new_names_are_free(self):
        """Aucun des nouveaux noms n'est déjà pris sur son modèle — sinon le
        renommage écraserait un champ existant."""
        fields = self.env['ir.model.fields'].sudo()
        for model, old, new, _ttype in _load_field_rename_map():
            existing = fields.search_count([('model', '=', model), ('name', '=', new)])
            if existing and fields.search_count(
                    [('model', '=', model), ('name', '=', old)]):
                self.fail('%s.%s existe déjà alors que %s est encore là'
                          % (model, new, old))

    def test_substitution_is_reversible(self):
        """Aller-retour sur les formes réellement rencontrées : domaine,
        arch de vue, chemin pointé, nom de méthode."""
        samples = [
            "[('x_studio_transport', '=', 'DPD')]",
            '<field name="x_studio_nb_palette" invisible="not x_studio_bl_groupe"/>',
            "{'search_default_x_studio_transport': 1}",
            "{'default_x_studio_bl_groupe': True}",
            "related='partner_id.x_studio_notes_internes'",
            "compute='_compute_x_studio_marge'",
            "def _compute_x_studio_marge(self):",
        ]
        for sample in samples:
            forward = _rename_helpers_in_text(_rename_fields_in_text(sample))
            self.assertNotIn(OLD_PREFIX, forward, sample)
            back = _rename_helpers_in_text(
                _rename_fields_in_text(forward, reverse=True), reverse=True)
            self.assertEqual(back, sample)

    def test_substitution_respects_word_boundaries(self):
        """Un nom qui en préfixe un autre ne doit pas être coupé en deux.

        x_studio_transport préfixe x_studio_transport_po : sans frontière de
        mot, le premier mangerait le second et le rollback ne retrouverait
        jamais le nom d'origine.
        """
        text = 'x_studio_transport x_studio_transport_po x_studio_transport_achat'
        renamed = _rename_fields_in_text(text)
        self.assertEqual(
            renamed,
            'ca_diff_transport ca_diff_transport_po ca_diff_transport_achat')
        self.assertFalse(re.search(r'\bca_diff_transport_po_', renamed))
        self.assertEqual(_rename_fields_in_text(renamed, reverse=True), text)

    def test_context_keys_are_renamed(self):
        """Un nom collé derrière une clé de contexte suit le renommage — c'est
        le cas que la seule frontière de mot laisse passer."""
        self.assertEqual(
            _rename_fields_in_text("{'search_default_x_studio_transport': 1}"),
            "{'search_default_ca_diff_transport': 1}")

    def test_unknown_names_are_left_alone(self):
        """Rien hors de la table de correspondance n'est touché — y compris un
        champ Studio d'une autre base, absent des sources."""
        text = "x_studio_champ_inconnu et ca_diff_autre_chose"
        self.assertEqual(_rename_fields_in_text(text), text)
        self.assertEqual(_rename_fields_in_text(text, reverse=True), text)
