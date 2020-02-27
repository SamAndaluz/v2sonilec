# -*- coding: utf-8 -*-

import json
import re
import uuid
from functools import partial

from lxml import etree
from dateutil.relativedelta import relativedelta
from werkzeug.urls import url_encode

from odoo import api, exceptions, fields, models, _
from odoo.tools import float_is_zero, float_compare, pycompat
from odoo.tools.misc import formatLang

from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning

from odoo.addons import decimal_precision as dp
import logging



_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    l10n_mx_edi_cfdi_name2 = fields.Char(copy=False)
    is_start_amount = fields.Boolean("Es saldo inicial",
        help="Si es True, esta factura es de saldos inciiales")

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice,self).action_invoice_open()
        for rec in self:
            if rec.l10n_mx_edi_cfdi_name2: #SI FUE CARGADA CON ESTE MODULO
                rec.l10n_mx_edi_cfdi_name = rec.l10n_mx_edi_cfdi_name2
        return res

    @api.multi
    def action_move_create(self):
        """
        HERENCIA DE METODO QUE CAMBIA NOMBRE DE APUNTE CONTABLE
        CUANDO ES UNA FACTURA CARGADA DESDE UN XML
        """
        res = super(AccountInvoice,self).action_move_create()
        for inv in self:
            if inv.l10n_mx_edi_cfdi_name2: #SI FUE CARGADA CON ESTE MODULO 
                if inv.type == 'out_invoice' or inv.type == 'out_refund':
                    inv.move_id.name = inv.name
                elif (inv.type == 'in_invoice' or inv.type == 'in_refund') and inv.is_start_amount:
                    inv.move_id.name = inv.reference
        return res



class AccountTax(models.Model):
    _inherit = 'account.tax'

    tax_code_mx = fields.Char(string='Codigo cuenta')

