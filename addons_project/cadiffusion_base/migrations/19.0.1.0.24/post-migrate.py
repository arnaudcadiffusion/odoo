"""
Migration 19.0.1.0.24 — post-upgrade

Recalcule le conditionnement des ordres de fabrication : il prenait le premier
élément de product.template.uom_ids (ordre de tri de uom.uom, donc la pièce
avant « CARTON DE 20 ») au lieu du plus grand carton du produit, comme les
lignes de vente et d'achat (_cadiffusion_carton_uom).
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    productions = env['mrp.production'].search([])
    env.add_to_compute(
        productions._fields['x_studio_conditionnement'], productions)
    productions.flush_recordset(['x_studio_conditionnement'])
