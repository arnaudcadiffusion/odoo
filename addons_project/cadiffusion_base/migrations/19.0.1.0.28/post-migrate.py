"""
Migration 19.0.1.0.28 — post-upgrade

Vérification d'intégrité du renommage complet (même garde-fou que la .27,
rejoué après le dernier lot) : lève, et annule l'upgrade avant commit, si une
colonne ca_diff_* porte moins de valeurs que la x_studio_* correspondante.
"""
from odoo.addons.cadiffusion_base.field_rename import _assert_field_rename_integrity


def migrate(cr, version):
    _assert_field_rename_integrity(cr)
