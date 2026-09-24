"""
Migration 19.0.1.0.32 - post-upgrade

1. Safety net of the rename, once the registry is loaded on the cad_* names:
   _repair_orphan_field_rename_data catches the databases the pre-migrate
   could not handle (both columns present), _assert_field_rename_integrity
   raises - and so cancels the upgrade before commit - if any data is left
   out of reach of the code.
2. Customer categories are no longer hardcoded: they live in
   ca.diffusion.customer.category, seeded from the former list and the
   values actually stored (_seed_lists, also run by the post_init_hook).
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base.field_rename import (
    _assert_field_rename_integrity,
    _repair_orphan_field_rename_data,
)


def migrate(cr, version):
    _repair_orphan_field_rename_data(cr)
    _assert_field_rename_integrity(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ca.diffusion.customer.category']._seed_lists()
