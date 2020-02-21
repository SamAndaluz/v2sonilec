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
    _inherit = "account.invoice"

    @api.depends('picking_ids')
    def _compute_picking_ids(self):
        for invoice in self:
            print('len(invoice.picking_ids): ',len(invoice.picking_ids))
            invoice.picking_count = len(invoice.picking_ids)

    picking_ids = fields.One2many('stock.picking', 'invoice_id', string='Movimientos')
    picking_count = fields.Integer(string='No. movimeintos', compute='_compute_picking_ids')

    create_return = fields.Boolean(string='Crear mov. de inventario', copy=False,
        default=True, 
        help='si se marca la casilla, se creara y validara mov. de inventario automaticamente')
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacen', copy=False, 
        help='Necesario para crear el mov. de almacen')


    @api.multi
    def action_view_picking(self):
        '''
        This function returns an action that display existing delivery orders
        of given sales order ids. It can either be a in a list or in a form
        view, if there is only one delivery order to show.
        '''
        print('action_view_picking')
        action = self.env.ref('stock.action_picking_tree_all').read()[0]

        pickings = self.mapped('picking_ids')
        print('len(pickings): ',len(pickings))
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            action['res_id'] = pickings.id
        return action


    def process_picking_errors(self, picking_vals, picking_type):
        """
        si existe algun error al intentar crear el picking
        este metodo muestra el mensaje descriptivo para el error
        process_picking_errors = diccionario con valores a crear
        picking_type = record con la infod e picking type
        """
        print('process_picking_errors')
        if not picking_type:
            raise ValidationError('Error al crear movimiento de almacen!\nEl almacen no pudo ser identificado, por favor seleccione uno!')
        if picking_type.code in ('internal','mrp_operaction'):
            raise ValidationError('Error al crear devolucion!\nEl tipo de operacion %s no es de tipo cliente/vendedor'%(picking_type.name))
        #tipo de entrada
        if picking_type.code == 'incoming':
            if not picking_vals.get('location_dest_id'):
                raise ValidationError('Error al crear movimiento de almacen!\nEl tipo de operacion %s no tiene una ubicacion destino definida'%(picking_type.name))
        #tipo de salida
        # if picking_type.code == 'outgoing':
        #     if not picking_vals.get('location_src_id'):
        #         raise ValidationError('Error al crear movimiento de almacen!\nEl tipo de operacion %s no tiene una ubicacion origen definida'%(picking_type.name))
        
        #tipo de salida
        # if picking_type.code == 'outgoing':
        #     if not picking_vals.get('location_dest_id'):
        #         raise ValidationError('El tipo de operacion %s no tiene una ubicacion de destino definida'%(picking_type.name))

        return
        
    def get_picking_locations(self, picking_type_id):
        """
        obtiene las ubicaciones origin y destino
        """
        print('get_picking_locations')
        location_id = False
        location_dest_id = False
        if picking_type_id:
            if picking_type_id.default_location_src_id:
                location_id = picking_type_id.default_location_src_id.id
            elif self.partner_id:
                if self.type in ('out_refund',):
                    location_id = self.partner_id.property_stock_customer.id
                elif self.type in ('in_invoice',):
                    location_id = self.partner_id.property_stock_supplier.id
            else:
                customerloc, location_id = self.env['stock.warehouse']._get_partner_locations()

            if picking_type_id.default_location_dest_id:
                location_dest_id = picking_type_id.default_location_dest_id.id
            elif self.partner_id:
                if self.type in ('in_refund',):
                    location_dest_id = self.partner_id.property_stock_supplier.id
                elif self.type in ('out_invoice',):
                    location_dest_id = self.partner_id.property_stock_customer.id
            else:
                location_dest_id, supplierloc = self.env['stock.warehouse'].sudo()._get_partner_locations()
        return location_id, location_dest_id


    @api.multi
    def set_picking_origin(self):
        """
        se establece el origen ya que la factura tiene un numero asignado
        """
        print('set_picking_origin')
        for invoice in self:
            pickings = invoice.picking_ids.filtered(lambda p: p.state == 'done')
            for picking in pickings:
                picking.origin = invoice.number
                print(str(picking.name)+', origin: '+picking.origin)
        return

    @api.multi
    def create_pickings(self):
        """
        se recorren facturas y se verifica si las facturas son notas de credito
        """
        print('create_pickings')
        #****proceso de creacion de pickings si es nota de credito****

        if self.create_return:
            # StockPicking = self.env['stock.picking'].sudo()
            StockPicking = self.env['stock.picking']

            #se recorren facturas y se verifica si las facturas son notas de credito
            for invoice in self:
                print('***',invoice.type)
                #if invoice.type in ('in_refund','out_refund'):

                picking_type = invoice.get_picking_type()
                line_vals = self.get_picking_lines()

                location_id, location_dest_id = self.get_picking_locations(picking_type)
                picking_vals = {
                    'partner_id': self.partner_id.id,
                    'picking_type_id': picking_type and picking_type.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'origin': invoice.number,
                    'move_lines': line_vals,
                    'invoice_id': invoice.id,
                    'is_return_picking': True,
                }
                self.process_picking_errors(picking_vals,picking_type)
                print('se va a crear picking')
                print('line_vals: ',line_vals)
                if line_vals != []:
                    picking = StockPicking.create(picking_vals)
                    print('picking_id: ', picking.id)
                    #validar picking:
                    picking.action_confirm()
                    picking.action_done()
                    print('done')
                    if picking.state != 'done':
                        raise ValidationError('Error al crear devolucion!\nEl movimiento de devolucion no pudo ser completado!')
        return
        
    def get_picking_lines(self):
        """
        obtiene lso valores que tendran
        las lienas del picking a crear
        """
        print('get_picking_lines')
        self.ensure_one()
        line_vals = []
        lines_exist = False #es true si al menos un producto es de tipo almacenable
        for line in self.invoice_line_ids:
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

    def get_picking_type(self):
        """
        obtiene el picking type dependiendo
        del tipo de factura y almacen (almacen se obtiene de so)
        """
        print('get_picking_type')
        self.ensure_one()
        picking_type = False
        warehouse = self.warehouse_id

        if warehouse:
            if self.type in ('in_refund','out_invoice'):
                picking_type = warehouse.out_type_id
            if self.type in ('out_refund','in_invoice'):
                picking_type = warehouse.in_type_id
        return picking_type


    @api.multi
    def action_invoice_open(self):
        """
        herencia de metodo
        si es asi, creara picking e intentara validarlo
        de no poder crear y validar el picking, devuelve mensaje de error
        """
        print('action_invoice_open')

        #se deja este fragmento de codigo para identificar las facturas que se revisaran
        to_open_invoices = self.filtered(lambda inv: inv.state != 'open')
        if to_open_invoices.filtered(lambda inv: inv.state != 'draft'):
            raise UserError(_("Invoice must be in draft state in order to validate it."))
        if to_open_invoices.filtered(lambda inv: float_compare(inv.amount_total, 0.0, precision_rounding=inv.currency_id.rounding) == -1):
            raise UserError(_("You cannot validate an invoice with a negative total amount. You should create a credit note instead."))

        #****proceso de creacion de pickings si es nota de credito****
        to_open_invoices.create_pickings()

        res = super(AccountInvoice, self).action_invoice_open()
        to_open_invoices.set_picking_origin()
        return res