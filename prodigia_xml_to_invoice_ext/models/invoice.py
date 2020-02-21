# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError,UserError
from datetime import datetime, timedelta


class AccountAccount(models.Model):
    _inherit = 'account.account'

    gas_default = fields.Boolean(string='Usar en lineas de combustibles')


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'


    def get_picking_lines(self):
        """
        sobrescritura de metodo de modulo
        prodigia_invoice_picking
        para ignorar las lineas donde
        ignore_line = True
        """
        print('get_picking_lines')
        self.ensure_one()
        line_vals = []
        lines_exist = False #es true si al menos un producto es de tipo almacenable
        for line in self.invoice_line_ids.filtered(lambda l: not l.ignore_line):
            if line.product_id and line.product_id.type == 'product':
                lines_exist = True
                line = (0,0, 
                    {
                    'product_id': line.product_id.id,
                    'name': line.product_id.display_name,
                    'product_uom': line.uom_id.id,
                    'product_uom_qty': line.quantity,
                    'quantity_done': line.quantity,
                    }
                )
                line_vals.append(line)
        return line_vals


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'


    ignore_line = fields.Boolean(string='Ignorar linea en mov de almacen',
        help='Ignorar linea al momento de generar un movimiento de almacen de esta factura')
