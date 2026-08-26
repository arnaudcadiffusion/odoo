"""
Migration 19.0.1.0.27 — post-upgrade

Vérification d'intégrité du lot transport : après le pre-migrate et le
chargement du registre, aucune donnée des champs renommés ne doit manquer.
Lève (et annule donc l'upgrade avant commit) au moindre écart.
"""
from odoo.addons.cadiffusion_base.field_rename import _assert_field_rename_integrity


def migrate(cr, version):
    _assert_field_rename_integrity(cr)
