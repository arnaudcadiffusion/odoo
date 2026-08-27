"""
Migration 19.0.1.0.29 — post-upgrade

Filet du retour arrière, après le chargement du registre sur les anciens noms.

1. _repair_orphan_field_rename_data rattrape les bases que le pre-migrate ne
   pouvait pas traiter faute de journal — typiquement une base restaurée d'un
   dump pris pendant que le renommage était en production : l'ORM vient d'y
   créer les colonnes x_studio_* vides, la donnée est encore dans les
   ca_diff_*, on la rapatrie.
2. _assert_field_rename_integrity lève, et annule donc l'upgrade avant commit,
   s'il reste la moindre colonne où la donnée dort hors d'atteinte du code.
"""
from odoo.addons.cadiffusion_base.field_rename import (
    _assert_field_rename_integrity,
    _repair_orphan_field_rename_data,
)


def migrate(cr, version):
    _repair_orphan_field_rename_data(cr)
    _assert_field_rename_integrity(cr)
