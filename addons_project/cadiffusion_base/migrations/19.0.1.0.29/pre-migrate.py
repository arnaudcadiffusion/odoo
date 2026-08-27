"""
Migration 19.0.1.0.29 — pre-upgrade

Retour arrière du renommage x_studio_* → ca_diff_*, parti en production par
les pre-migrates .27 (lot transport), .28 (le reste) et 19.0.1.0.1 de
public_tender (tender.order). Les sources de cette version sont revenues aux
noms x_studio_* : la base doit suivre AVANT que le registre ne se recharge,
sinon l'ORM crée des colonnes x_studio_* vides à côté des ca_diff_* pleines et
la donnée devient invisible sans que rien ne le signale.

Le rollback s'appuie sur le journal cadiffusion_field_rename : il n'inverse
que ce qui a réellement été appliqué (colonnes, ir_model_fields, xmlids,
filtres, exports, arch de vues, domaines et code des actions serveur), lot par
lot. _rollback_field_rename_batches les défait TOUS — un seul appel à
_rollback_field_rename ne prendrait que le dernier.

Idempotent : sans journal, ou avec tous les lots déjà soldés, ne fait rien.
Une base sans journal mais restaurée d'un dump renommé est rattrapée en
post-migrate par _repair_orphan_field_rename_data.
"""
from odoo.addons.cadiffusion_base.field_rename import _rollback_field_rename_batches


def migrate(cr, version):
    _rollback_field_rename_batches(cr)
