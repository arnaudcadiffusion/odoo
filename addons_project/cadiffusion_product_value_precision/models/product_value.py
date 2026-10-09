from odoo import fields, models


class ProductValue(models.Model):
    """``product.value`` records the manual cost corrections and is the starting
    point of the next full average-cost recomputation
    (``product.product._run_average_batch``).

    In core the ``value`` field is a Monetary, so a unit cost such as 0.0129 is
    rounded to the company currency (0.01) by the ORM itself, before anything
    else happens: there is no explicit ``currency.round`` in ``stock_account``
    that could be overridden instead. The next recomputation then restarts from
    the rounded figure and the average cost drifts.

    Redefining the field as a Float on the "Product Price" precision keeps the
    correction as typed. Accounting is untouched: journal items are built from
    ``stock.move.value``, which stays a Monetary.
    """
    _inherit = 'product.value'

    value = fields.Float(string='Value', digits='Product Price', required=True)
