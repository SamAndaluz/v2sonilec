# -*- coding: utf-8 -*-
{
    'name': "Customizaciones para modulo de importacion de xmls",

    'summary': """
       Modifica el comportamiento del modulo de importacion de xmls
       """,

    'description': """
       Modifica el comportamiento del modulo de importacion de xmls:
       -Cambia la forma de busqueda de productos (se busca por el campo custom_name)
       -La nomenclatura de los valores de custom_name: "nombre1|nombre2|nombre3|nombre4"
       -No permite creacion de productos, se detendra el proceso de no encontrar alguno
       -Se agrega campo almacen en wizard de importacion, este dato caera en la factura
       -Las facturas que tengan termino de pago de contado, se cargaran en estado pagado automaticamente
    """,

    'author': "Prodigia",
    'website': "http://prodigia.mx",
    'category': 'Invoicing',
    'version': '1.0.2',

    'maintainer': "Marco Cid",

    'depends': [
        'prodigia_xml_to_invoice',
        'stock_account',
        'prodigia_invoice_picking',
        ],

    'data': [
        'security/ir.model.access.csv',
        'views/account_views.xml',
        'views/xml_import_views.xml',
        'views/product_views.xml',
        'views/company_views.xml',       
    ],
    'demo': [
    ],
    'installable': True,
    'auto_install': False,
}