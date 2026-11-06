"""
Migration 19.0.1.0.34 - pre-upgrade

Mail and SMS templates join the text targets of the x_studio_* -> cad_*
rename: the Studio template "Confirmation Envoi" still rendered
``object.x_studio_n_commande`` and its automation blocked every delivery
validation. On a database renamed by 19.0.1.0.32 before this fix, the
templates are rewritten here; elsewhere 19.0.1.0.32 now covers them.

Idempotent. Undone by _rollback_field_rename_batches like any other batch.
"""
from odoo.addons.cadiffusion_base.field_rename import _catch_up_text_targets


def migrate(cr, version):
    _catch_up_text_targets(cr)
