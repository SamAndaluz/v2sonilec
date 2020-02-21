# -*- coding: utf-8 -*-
# Copyright 2019 Piotr Cierkosz (https://www.cier.tech)
{
    'name' : "Hide product description in Sale, Purchase and Accounting",
    'version' : "1.0.1",
    'images': ['images/thumbnail.png'],
    'author' : "Piotr Cierkosz",
    'category': 'Sales',
    'price': 25.0,
    'currency': 'EUR',
    'depends' : ['account', 'purchase', 'sale_management'],
    'installable' : True,
    'description' : "Hide product description in Sale, Purchase and Accounting",
    'website': "https://www.cier.tech",
    'summary': 'Hide product description in Sale, Purchase and Accounting',
    'data': [
    'views/ct_hide_desc_inv.xml',
    'views/ct_hide_desc_sol.xml',
    'views/ct_hide_desc_sol0.xml',
    'views/ct_hide_desc_purchase.xml',
    ],
#    'live_test_url': 'https://youtu.be/IuHSgOcBm4M',
    'license': 'Other proprietary',
}
