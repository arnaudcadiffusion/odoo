"""
Migration 19.0.1.0.30 — post-upgrade

The preparer field choices (transfers and MOs) are no longer hardcoded:
they live in ca.diffusion.preparer. Seed the lists from the historical
values of the code and the values actually stored (_seed_lists, also run by
the post_init_hook for fresh installs). Idempotent, never destructive.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ca.diffusion.preparer']._seed_lists()
