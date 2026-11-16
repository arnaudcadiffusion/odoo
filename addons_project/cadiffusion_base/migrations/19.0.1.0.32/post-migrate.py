"""
Migration 19.0.1.0.32 — post-upgrade

The "Bloquer" tick of the quotation form is a Studio field that only exists
in the production database. It read credit_on_hold on the order's customer,
while the hold is only ticked on the main customer record: an order placed
on a delivery or invoice address showed nothing. Make it read the commercial
partner (task#19578). Idempotent, does nothing where the field is absent.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['sale.order']._bloquer_follow_commercial_partner()
