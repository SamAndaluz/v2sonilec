# -*- coding: utf-8 -*-
from odoo import api, exceptions, fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"


    xml_import_line_ids = fields.One2many('res.company.xml.import.line',
                                    'company_id',
                                    string='Configuracion de importacion de xmls')



class ResCompanyXmlImportLine(models.Model):
    _name = 'res.company.xml.import.line'


    company_id = fields.Many2one('res.company', string='Compañia',required=True,)
    xml_import_analytic_account_id = fields.Many2one('account.analytic.account',
        string='Cuenta analitica',
        required=True,
        help='Esta cuenta analitica se utilizara pra las facturas improtadas con el importador de xmls')
    xml_import_warehouse_id = fields.Many2one('stock.warehouse',
        string='Almacen',
        required=True,
        help='Este almacen se utilizara para hacer los movimientos de inventario ' + \
        'que se generen en las facturas improtadas con el modulo de importacion de xmls')
    xml_import_journal_id = fields.Many2one('account.journal',
        string='Diario',
        required=True,
        help='Este diario se utlizara en las facturas importadas con el importador de xmls')