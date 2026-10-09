{
    'name': 'CaDiffusion Product Value Precision',
    'version': '19.0.1.0.0',
    'summary': 'Manual cost corrections keep the "Product Price" precision instead of the currency rounding',
    'category': 'Custom',
    'author': 'Cadiffusion',
    'depends': ['stock_account'],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
