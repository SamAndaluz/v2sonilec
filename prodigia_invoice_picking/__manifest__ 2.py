# -*- coding: utf-8 -*-
{
    'name': "Creacion de movimeintos de almacen al validar Facturas",

    'summary': """
        Creacion de movimeintos de almacen al validar Facturas""",

    'description': """
        Se agrega funcionalidad de que al validar una factura, se cree una salida de inventario
        y se valide automaticamente

        Se agregan los campos en factura (solo visibles si se tiene el permiso 'Creacion de movimientos de lamacen en facturas'):
        -almacen = necesario para crear el mov de inventario
        -crear mov. de inventario = indica si se desea crear un mov. de inventario al validar la factura
    """,

    'author': "Prodigia",
    'website': "http://www.prodigia.com.mx",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Account',
    'version': '0.1.0',

    # any module necessary for this one to work correctly
    'depends': ['stock_account','sale_stock',],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'security/groups.xml',
        'views/account_views.xml',
    ],
    # only loaded in demonstration mode
}