"""
Migration 19.0.1.0.3 - pre-upgrade

Renames the six tender.order fields this module declares (x_studio_* ->
cad_*, "Tri champs studio v15" agreed with the customer).

It has to happen HERE and not in cadiffusion_base: public_tender loads before
it (cadiffusion_base depends on it), and its _auto_init would create empty
cad_* columns next to the filled x_studio_* ones before the pre-migrate
19.0.1.0.32 of cadiffusion_base runs.

The mechanics (journal, rollback) live in cadiffusion_base/field_rename.py -
see its header. Idempotent.
"""
from odoo.addons.cadiffusion_base.field_rename import (
    TENDER_BATCH,
    _apply_field_rename,
)


def migrate(cr, version):
    _apply_field_rename(cr, only=TENDER_BATCH)
