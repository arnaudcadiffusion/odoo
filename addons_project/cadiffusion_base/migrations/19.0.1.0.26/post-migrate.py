"""
Migration 19.0.1.0.26 — post-upgrade

Recalcule mrp.production.ca_diff_conditionnement, devenu Many2one(uom.uom)
(voir pre-migrate.py) : le plus grand carton du produit, comme les lignes de
vente et d'achat.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    productions = env['mrp.production'].search([])
    env.add_to_compute(
        productions._fields['ca_diff_conditionnement'], productions)
    productions.flush_recordset(['ca_diff_conditionnement'])
