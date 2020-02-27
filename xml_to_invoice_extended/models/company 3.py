# -*- coding: utf-8 -*-
from odoo import api, exceptions, fields, models, _


class ResCompanyXmlImportLine(models.Model):
    _inherit = 'res.company.xml.import.line'
    
    xml_import_bank_id = fields.Many2one('account.journal',
        string='Banco',
        required=True,
        domain="[('type','=','bank')]",
        help='Este banco se utlizara en las facturas importadas con el importador de xmls')