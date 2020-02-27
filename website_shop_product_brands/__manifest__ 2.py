# -*- coding: utf-8 -*-
{
    'name': "Website Product Brand",
    'summary': "Website Product Brand",
    'description': """
Website Product Brand
===============================================
Website Product Brand.
    """,

    'author': 'iPredict IT Solutions Pvt. Ltd.',
    'website': 'http://ipredictitsolutions.com',
    "support": "ipredictitsolutions@gmail.com",

    'category': 'eCommerce',
    'version': '12.0.0.1.0',
    'depends': ['product', 'sale', 'website_sale'],

    'data': [
        'security/ir.model.access.csv',
        'views/assets.xml',
        'views/product_brand_view.xml',
        'views/product_view.xml',
        'views/website_brand_view.xml',
        'views/website_products_attributes.xml',
        'views/website_brand_snippets.xml',
    ],

    'license': "OPL-1",
    'price': 25,
    'currency': "EUR",

    "installable": True,

    'images': ['static/description/main.png'],
}
