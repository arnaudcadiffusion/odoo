from . import models

MIN_PRODUCT_PRICE_DIGITS = 4


def post_init_hook(env):
    """Manual cost corrections are stored on the "Product Price" precision:
    make sure it offers at least 4 decimals."""
    precision = env['decimal.precision'].search([('name', '=', 'Product Price')], limit=1)
    if precision and precision.digits < MIN_PRODUCT_PRICE_DIGITS:
        precision.digits = MIN_PRODUCT_PRICE_DIGITS
