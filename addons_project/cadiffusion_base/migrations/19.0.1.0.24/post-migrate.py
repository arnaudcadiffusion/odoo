"""
Migration 19.0.1.0.24 — post-upgrade

price_reduce_taxexcl is now stored with the "Product Price" precision
(4 decimals) instead of the currency rounding. The values already stored
were rounded to 2 decimals: recompute them from price_subtotal / quantity.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env["sale.order.line"].search([])
    env.add_to_compute(lines._fields["price_reduce_taxexcl"], lines)
    lines.flush_model(["price_reduce_taxexcl"])
