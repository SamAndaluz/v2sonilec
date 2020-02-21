# -*- coding: utf-8 -*-
{
    'name': "Carga de facturas por XMLs V12",

    'summary': """
       Modulo que permite la carga y validacion de facturas 
       al importar un archivo .zip que contenga xml de facturas
       """,

    'description': """
       Modulo que permite la carga y validacion de facturas 
       al importar un archivo .zip que contenga xml de facturas
    """,

    'author': "Prodigia",
    'website': "http://prodigia.mx",
    'category': 'Invoicing',
    'version': '1.0.2',

    'maintainer':"Marco Cid",

    # dependencias
    'depends': [
        # 'account_invoicing',
        # 'account_cancel',
        'crm',
        'sale_management',
        'account_accountant',
        'base_vat',
        'base_address_extended',
        'document',
        'base_address_city',
        'l10n_mx_edi',
        'stock',
        #'l10n_mx',
        ],

    # always loaded
    'data': [
        'views/views.xml',
        'views/partner_views.xml',         
    ],
    # only loaded in demonstration mode
    'demo': [
    ],
    'installable': True,
    'auto_install': False,
}