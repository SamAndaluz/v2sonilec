# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError,UserError
from datetime import datetime, timedelta

import xmltodict

import base64
import zipfile
import io

from suds.client import Client
import random
import pdb


class XmlImportWizard(models.TransientModel):
    _inherit = 'xml.import.wizard'


    # def _get_default_invoice_account_id(self):
    #     print('_get_default_invoice_account_id')
    #     company_id = self.env.user.company_id
    #     print('company_id: ',company_id.name)
    #     AccountInvoice = self.env['account.invoice']
    #     domain = [('company_id','=',company_id.id),('state','not in',('cancel',))]
    #     invoice = AccountInvoice.search(domain, order="create_date desc", limit=1)
    #     account_id = invoice and invoice.account_id and invoice.account_id.id or False
    #     return account_id


    @api.onchange('invoice_type','company_id')
    def _onchange_invoice_type(self):
        """
        obtiene datos de la ultima factura
        no cancelada
        de la compañia
        """
        print('_onchange_invoice_type')
        company_id = self.env.user.company_id
        print('company_id: ',company_id.name)
        AccountInvoice = self.env['account.invoice']
        domain = [('company_id','=',company_id.id),
                    ('state','in',('paid',)),
                    ('company_id','=',company_id.id),
                    ('type','=',self.invoice_type),
                ]
        invoice = AccountInvoice.search(domain, order="create_date desc", limit=1)
        payment = invoice.payment_ids and invoice.payment_ids[0] or False
        
        self.payment_journal_id = payment and payment.journal_id and payment.journal_id.id or False

        # if invoice:
        print('invoice: ',invoice.name)
        account_id = invoice.account_id and invoice.account_id.id or False
        line_data = invoice.invoice_line_ids.filtered(lambda l: l.product_id and l.account_id)
        
        self.invoice_account_id = account_id
        self.line_account_id = line_data and line_data[0].account_id.id or False
        tag_ids = line_data and line_data[0].analytic_tag_ids.ids or False
        print('tag_ids:',tag_ids)
        if tag_ids:
            self.line_analytic_tag_ids = [(6, None, tag_ids)]
        print('self.invoice_type: ',self.invoice_type)
        if self.invoice_type == 'out_invoice':
            self.user_id = invoice and invoice.user_id and invoice.user_id.id or False
            self.team_id = invoice and invoice.team_id and invoice.team_id.id or False

        if self.invoice_type == 'in_invoice':
            print('de proveedores')
            self.team_id = False
            self.user_id = False
            self.warehouse_id = invoice and invoice.warehouse_id and invoice.warehouse_id.id or False
            self.journal_id = invoice and invoice.journal_id and invoice.journal_id.id or False




    #sobrescritura de campos para agregar valores por defecto
    # invoice_account_id = fields.Many2one('account.account',
    #     string='Cuenta de Factura',
    #     #default=_get_default_invoice_account_id,
    #     required=True)

    #Sobrescritura de campos, ya no se usaran
    # sat_validation = fields.Boolean(string='Validar en SAT',
    #     default=False)
    import_type = fields.Selection(
        [('start_amount','Saldos Iniciales'),
        ('regular','Factura regular')],
        string='Tipo de Importacion',
        required=True,
        default='regular')
    create_product = fields.Boolean(string='Crear productos',
        help='Si el producto no se encuentra en Odoo, crearlo automaticamente',
        default=True)

    #Campos tecnicos
    products_valid = fields.Boolean(default=True,
        help='Campo tecnico que indica si los productos en el xml estan cargados en Odoo')
    products_error_msg = fields.Text(
        help='Campo tecnico que contendra listado de productos no encontrados en Odoo',
        default="Los siguientes productos no fueron encontrados:\n")

    #el almacen se usara para que se creen los movmientos de inventario pertinentes
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacen', copy=False, 
        help='Necesario para crear el mov. de almacen', required=False)
    payment_journal_id = fields.Many2one('account.journal',
        string='Diario de pago', required=True)

    journal_id = fields.Many2one('account.journal',
        string='Diario',
        required=False)


    def get_extra_line_tax(self):
        """
        busca impuesto de tipo exento y lo devuelve
        """
        AccountTax = self.env['account.tax']
        type_tax_use = 'sale' if self.invoice_type == 'out_invoice' else 'purchase'
        res = AccountTax.search([('l10n_mx_cfdi_tax_type','=','Exento'),
                                ('type_tax_use','=',type_tax_use),
                                ('company_id','=',self.company_id.id),])
        return res and res[0] or False


    def get_extra_line_account(self):
        """
        busca cuenta para la liena extra
        """
        AccountAccount = self.env['account.account']
        res = AccountAccount.search([('gas_default','=',True),('company_id','=',self.company_id.id)])
        return res and res[0] or False
            


    def get_cfdi32(self, products, taxes, default_account, analytic_account_id):
        """
        SE SOBRESCRIBE PARA AGREGAR INFO DE CUENTA ANALITICA
        """
        if not isinstance(products, list):
            products = [products]
        #print('products: ',products)
        all_products = []
        amount = 0
        for product in products:
            amount += (float(product.get('@importe',0)) - float(product.get('@descuento',0)))

        #print('amount: ',amount)


        taxes = self.get_tax_ids(taxes,'3.2')
        invoice_line = {}
        invoice_line['name'] = 'SALDOS INICIALES'
        invoice_line['quantity'] = 1

        analytic_tag_ids = False
        if self.line_analytic_tag_ids:
            analytic_tag_ids = [(6, None, self.line_analytic_tag_ids.ids)]

        invoice_line['analytic_tag_ids'] = analytic_tag_ids
        invoice_line['account_analytic_id'] = analytic_account_id
        invoice_line['account_id'] = default_account or self.line_account_id.id
        invoice_line['price_subtotal'] = amount
        invoice_line['price_unit'] = amount
        invoice_line['taxes'] = taxes
        all_products.append(invoice_line)
        return [invoice_line]


    def add_products_to_invoice(self, products, default_account, account_analytic_id):
        '''
            Obtener datos de los productos (Conceptos).
            SE SOBRESCRIBE PARA AGREGAR INFO DE CUENTA ANALITICA
        '''
        all_products = []

        # asegurarse de que `products` es una lista
        # para poder iterar sobre ella
        if not isinstance(products, list):
            products = [products]

        exent_tax = self.get_extra_line_tax()
        exent_tax = exent_tax and exent_tax.id or False
        extra_line_account_id = self.get_extra_line_account()

        # crear un dict para cada producto en los conceptos
        for product in products:
            # datos básicos
            invoice_line = {}

            extra_line = {} #se usara para productos gasolina, contendra lineas extra
            
            invoice_line['name'] = product.get('@Descripcion') or product.get('@descripcion')
            invoice_line['quantity'] = product.get('@Cantidad') or product.get('@cantidad')
            invoice_line['price_subtotal'] = product.get('@Importe') or product.get('@importe')
            invoice_line['price_unit'] = product.get('@ValorUnitario') or product.get('@valorUnitario')

            #datos para creacion de producto
            invoice_line['sat_product_ref'] = product.get('@ClaveProdServ') or product.get('@claveProdServ')
            invoice_line['product_ref'] = product.get('@NoIdentificacion') or product.get('@noIdentificacion')
            invoice_line['sat_uom'] = product.get('@ClaveUnidad') or product.get('@claveUnidad')

            analytic_tag_ids = False
            if self.line_analytic_tag_ids:
                analytic_tag_ids = [(6, None, self.line_analytic_tag_ids.ids)]

            invoice_line['analytic_tag_ids'] = analytic_tag_ids
            invoice_line['account_analytic_id'] = account_analytic_id
            invoice_line['account_id'] = default_account or self.line_account_id.id

            # calcular porcentaje del descuento, si es que hay 
            if product.get('@Descuento'):
                invoice_line['discount'] = self.get_discount_percentage(product)
            else:
                invoice_line['discount'] = 0.0

            # obtener id del producto
            # crear producto si este no existe
            invoice_line['product_id'] = self.get_product_or_create(invoice_line)

            # si el producto tiene impuestos, obtener datos
            # y asignarselos al concepto
            tax_group = ''
            check_taxes = product.get('cfdi:Impuestos')
            if check_taxes:
                invoice_taxes = []
                if check_taxes.get('cfdi:Traslados'):
                    traslado = {}
                    t = check_taxes['cfdi:Traslados']['cfdi:Traslado']
                    #print('---t----: ',t)
                    if not isinstance(t,list):
                        t = [t,]
                    for element in t:
                        # revisa rsi es gasolina el producto
                        tax_base = element.get('@Base')
                        # si la base del impuesto no coincide con el subtotal del producto
                        # es que es gasolina
                        if tax_base != invoice_line['price_subtotal']:
                            print("es gasolina")
                            new_price = float(tax_base) / float(invoice_line['quantity'])
                            invoice_line['price_unit'] = new_price

                            #calcular precio de linea extra
                            extra_line_price = float(invoice_line['price_subtotal']) - float(tax_base)

                            #revisar si no es necesario recalcular el subtotal
                            # invoice_line['price_unit'] = new_price * invoice_line['quantity']

                            extra_account_id = extra_line_account_id and extra_line_account_id.id or False
                            if not extra_account_id:
                                raise ValidationError('No se encontro una cuenta de combustible configurada')

                            #crear linea extra
                            extra_line = {
                                'name': invoice_line['name'],
                                'quantity': 1,
                                #'product_id': invoice_line['product_id'],
                                'price_unit': extra_line_price,
                                'price_subtotal': extra_line_price,
                                'sat_product_ref': invoice_line['sat_product_ref'],
                                'product_ref': invoice_line['product_ref'],
                                'sat_uom': invoice_line['sat_uom'],
                                'ignore_line': True,
                                'account_id': extra_line_account_id and extra_line_account_id.id or False,
                                'account_analytic_id': account_analytic_id,
                                'analytic_tag_ids': False,
                            }

                            if exent_tax:
                                extra_line['taxes'] = [(6, None, (exent_tax,))]

                        tax_code = element.get('@Impuesto','')
                        tax_rate = element.get('@TasaOCuota','0')
                        tax_factor = element.get('@TipoFactor','')
                        tax_group =  tax_group + tax_code + '|' + tax_rate + '|tras|' + tax_factor + ','
                        #print('tax_group: ',tax_group)
                        #tax = self.get_tax_ids(tax_group)
                        #print('tax: ',tax)
                        #traslado['tax_id'] = tax
                        #invoice_taxes.append(tax)

                if check_taxes.get('cfdi:Retenciones'):
                    retencion = {}
                    r = check_taxes['cfdi:Retenciones']['cfdi:Retencion']
                    #print('---r----: ',r)
                    if not isinstance(r,list):
                        r = [r,]
                    for element in r:
                        #retencion['amount'] = element.get('@Importe') or element.get('@importe')
                        #retencion['base'] = element.get('@Base')
                        #retencion['account_id'] = 23
                        tax_code = element.get('@Impuesto','')
                        tax_rate = element.get('@TasaOCuota','0')
                        tax_factor = taxelementes.get('@TipoFactor','')
                        tax_group =  tax_group + tax_code + '|' + tax_rate + '|ret|' + tax_factor + ','
                        #print('tax_group: ',tax_group)
                        #tax = self.get_tax_ids(tax_group)
                        #print('tax: ',tax)
                        #retencion['tax_id'] = tax
                        #invoice_taxes.append(tax)
                taxes = False
                if tax_group:
                    taxes = self.get_tax_ids(tax_group)
                #print('taxes: ',taxes)
                invoice_line['taxes'] = taxes

            # agregar concepto a la lista de conceptos
            all_products.append(invoice_line)

            #se agrega linea extra, de existir
            if extra_line:
                all_products.append(extra_line)
        
        return all_products



    def prepare_invoice_data(self, bill):
        '''
            Obtener datos del XML y wizard para llenar factura
            Returns:
                invoice: datos generales de la factura.
                invoice_line: conceptos de la factura.
        '''
        
        # aquí se guardaran los datos para su posterior uso
        invoice = {}
        invoice_line = []
        partner = {}

        filename = bill['filename']

        # elementos principales del XML
        root = bill['xml']['cfdi:Comprobante']

        # revisa version
        version = root.get('@Version') or root.get('@version') or ''
        #print('root: ',root)
        #print('version: ',version)

        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            # xml de cliente
            vendor = root['cfdi:Receptor']
            vendor2 = root['cfdi:Emisor']
        else:
            # xml de proveedor
            vendor = root['cfdi:Emisor']
            vendor2 = root['cfdi:Receptor']

        #obtener datos del partner
        partner['rfc'] = vendor.get('@Rfc') or vendor.get('@rfc')
        invoice['rfc'] = vendor.get('@Rfc') or vendor.get('@rfc')
        invoice['company_rfc'] = vendor2.get('@Rfc') or vendor2.get('@rfc')
        partner['name'] = vendor.get('@Nombre',False) or vendor.get('@nombre','PARTNER GENERICO: REVISAR')
        partner['position_id'] = vendor.get('@RegimenFiscal')
        partner_rec = self.get_partner_or_create(partner)
        default_account = partner_rec.default_xml_import_account and \
                    partner_rec.default_xml_import_account.id or False
        #print('default_account: ',default_account)
        partner_id = partner_rec.id


        serie = root.get('@Serie') or root.get('@serie')
        folio = root.get('@Folio') or root.get('@folio')
        metodopago = root.get('@MetodoPago') or root.get('@metodoPago') or False
        forma_pago = root.get('@FormaPago') or root.get('@formaPago')
        uso_cfdi = root['cfdi:Receptor'].get('@UsoCFDI') or root['cfdi:Receptor'].get('@usoCFDI')

        journal_id, analytic_account_id, warehouse_id =self.get_company_xml_import_data(serie)
        invoice['journal_id'] = journal_id
        invoice['warehouse_id'] = warehouse_id
        invoice['metodo_pago'] = metodopago

        forma_pago_rec = self.get_edi_payment_method(forma_pago)
        print('forma_pago_rec: ',forma_pago_rec)
        print('uso_cfdi: ',uso_cfdi)
        invoice['l10n_mx_edi_payment_method_id'] = forma_pago_rec and forma_pago_rec.id or False
        invoice['l10n_mx_edi_usage'] = uso_cfdi

        # obtener datos de los conceptos.
        # invoice_line es una lista de diccionarios
        #invoice_line = self.add_products_to_invoice(root['cfdi:Conceptos']['cfdi:Concepto'])
        #11 nov/14B60424-DED8-4279-BB00-7BDE3BBB4BB7.xml
        if self.import_type == 'start_amount':
            #print('filename: ',filename)
            # carga de saldfos iniciales, las lineas se agrupan por impuesto
            if version == '3.3':
                invoice_line = self.compact_lines(root['cfdi:Conceptos']['cfdi:Concepto'], default_account)
            else:
                #print('111111')
                taxes = self.get_cfdi32_taxes(root['cfdi:Impuestos'])
                invoice_line = self.get_cfdi32(root['cfdi:Conceptos']['cfdi:Concepto'], taxes, default_account, analytic_account_id)
        else:
            # carga de factura regular
            invoice_line = self.add_products_to_invoice(root['cfdi:Conceptos']['cfdi:Concepto'], default_account, analytic_account_id)

        # obtener datos de proveedor
        # crear al proveedor si no existe
        # #print('VENDOR: ',vendor.get('@Nombre'))
        # #print('VENDOR: ',vendor.get('@nombre'))
        tipo_comprobante = root.get('@TipoDeComprobante') or root.get('@tipoDeComprobante')
        invoice['tipo_comprobante'] = tipo_comprobante
        #SE CORRIGE TIPO SEGUN EL TIPO DE COMPROBANTE
        # SOLO TOMA EN CUENTA INGRESOS Y EGRESOS
        #print('tipo_comprobante: ',tipo_comprobante)
        corrected_invoice_type = False
        if tipo_comprobante.upper() == 'E':
            if self.invoice_type == 'out_invoice':
                #print('out_refund')
                corrected_invoice_type = 'out_refund'
            else:
                #print('in_refund')
                corrected_invoice_type= 'in_refund'



        # partner['rfc'] = vendor.get('@Rfc') or vendor.get('@rfc')
        # invoice['rfc'] = vendor.get('@Rfc') or vendor.get('@rfc')
        # invoice['company_rfc'] = vendor2.get('@Rfc') or vendor2.get('@rfc')
        # partner['name'] = vendor.get('@Nombre',False) or vendor.get('@nombre','PARTNER GENERICO: REVISAR')

        # partner['position_id'] = vendor.get('@RegimenFiscal')
        # partner_id = self.get_partner_or_create(partner)
        moneda = root.get('@Moneda') or root.get('@moneda') or 'MXN'
        #print('moneda.upper(): ',moneda.upper())
        if moneda.upper() in ('M.N.','XXX','PESO MEXICANO'):
            moneda = 'MXN'

        # obtener datos generales de la factura
        currency = self.env['res.currency'].search([('name', '=', moneda)])
        #print('self.invoice_type: ',self.invoice_type)
        #invoice['type'] = 'in_invoice' # factura de proveedor

        invoice['type'] = corrected_invoice_type or self.invoice_type

        invoice['name'] = folio
        if serie:
            invoice['name'] = serie + ' ' + folio

        invoice['amount_untaxed'] = root.get('@SubTotal') or root.get('@subTotal')
        invoice['amount_total'] = root.get('@Total') or root.get('@total')
        invoice['partner_id'] = partner_id
        invoice['currency_id'] = currency.id
        invoice['date_invoice'] = root.get('@Fecha') or root.get('@fecha')
        #invoice['account_id'] = self.env['account.invoice']._default_journal().id

        ####
        invoice['l10n_mx_edi_cfdi_name'] = filename
        #invoice['l10n_mx_edi_cfdi_name2'] = filename #DENOTA QUE SE CARGO POR MEDIO DE ESTE MODULO
        #invoice['journal_id'] = self.journal_id and self.journal_id.id or False
        invoice['team_id'] = self.team_id and self.team_id.id or False
        invoice['user_id'] = self.user_id and self.user_id.id or False
        invoice['account_id'] = self.invoice_account_id.id
        #print('invoice_line: ',invoice_line)
        #OBTENER UUID
        uuid = root['cfdi:Complemento']['tfd:TimbreFiscalDigital'].get('@UUID')
        #print(root['cfdi:Complemento']['tfd:TimbreFiscalDigital'])
        #print('UUID: ',uuid)
        invoice['uuid'] = uuid
        return invoice, invoice_line, version


    def get_edi_payment_method(self, code):
        """
        busca metodo de pago a partir de codigo 
        y lo devuelve
        """
        print('get_edi_payment_method: ',code)
        PaymentMethod = self.env['l10n_mx_edi.payment.method']
        res = PaymentMethod.search([('code','=',code)])
        return res and res[0] or False


    def get_company_xml_import_data(self, serie=False):
        """
        -para xmls de cliente
        obtiene el diario, almacen, cuenta analitica
        segun la serie

        -para xmls de proveedor:
        obtiene el diario del wizard

        regresa jorunal_id, analytic_account_id, warehouse_id
        """
        #print('get_company_xml_import_data')
        #print('---> SERIE: ',serie)
        journal_id = False
        analytic_account_id = False
        warehouse_id = False
        if self.invoice_type == 'out_invoice':
            if not serie:
                raise ValidationError('El xml no contiene el atributo serie')
            for line in self.company_id.xml_import_line_ids:
                if line.xml_import_journal_id.sequence_id.name == serie:
                    journal_id = line.xml_import_journal_id.id
                    analytic_account_id = line.xml_import_analytic_account_id.id
                    warehouse_id = line.xml_import_warehouse_id.id
                    break
            # for journal in self.company_id.xml_import_journal_ids:
            #     if journal.sequence_id.name == serie:
            #         journal_id = journal.id
            #         break
            else:
                raise ValidationError('No se encontro un diario configurado con la serie {} en la compañia seleccionada\nPor favor configure uno!'.format(serie))
        else:
            journal_id = self.journal_id.id
            analytic_account_id = self.line_analytic_account_id.id
            warehouse_id = self.warehouse_id and self.warehouse_id.id or False
        return journal_id, analytic_account_id, warehouse_id



    def valdiate_duplicate_invoice(self,vat,amount_total,date,invoice_name):
        """
        REVISA SI YA EXISTE LA FACTURA EN SISTEMA
        DEVUELVE TRUE SI YA EXISTE
        FALSE SI NO
        """

        #print('vat: ',vat)
        #print('amount_total: ',amount_total)
        
        #print('invoice_name: ',invoice_name)
        print("valdiate_duplicate_invoice")
        date = date.split('T')[0]
        #print('date: ',date)
        AccountInvoice = self.env['account.invoice'].sudo()
        domain = [
            ('partner_id.vat','=',vat),
            ('amount_total','=',round(float(amount_total),2)),
            ('date_invoice','=',date),
            ('state','!=','cancel'),
        ]
        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            #FACTURA CLIENTE
            domain.append(('name','=',invoice_name))
        else:
            #FACTURA PROVEEDOR
            domain.append(('reference','=',invoice_name))
        invoices = AccountInvoice.search(domain)
        #print('domain: ',domain)
        #print('invoices: ',invoices)

        test_invoice = AccountInvoice.search([('id','=',3048)])
        #print('test_invoice.date: ',test_invoice.date)
        if invoices:
            print('DUPLICADA: ',invoices)
            return True
        return False



    @api.multi
    def validate_bills(self):
        '''
        Se sobrescribe funcion principal
        para agergar logica de productos no encontrados
        ''' 
        file_ext = self.get_file_ext(self.filename)
        if file_ext.lower() not in ('xml','zip'):
            raise ValidationError('Por favor, escoja un archivo ZIP o XML')

        raw_file = self.get_raw_file()
        zip_file = self.get_zip_file(raw_file)

        if zip_file:
            # extraer archivos dentro del .zip
            bills = self.get_xml_from_zip(zip_file)
        else:
            bills = self.get_xml_data(raw_file)

        # print("bills: \n",bills)
        for bill in bills:
            invoice, invoice_line, version = self.prepare_invoice_data(bill)
            bill['invoice_data'] = invoice
            bill['invoice_line_data'] = invoice_line
            bill['version'] = version

            #valida que el tipo de comprobante no sea P
            if invoice['tipo_comprobante'] != 'P':
                bill['valid'] = True
            else:
                bill['valid'] = False
                bill['state'] = 'Tipo de comprobante no valido: "P"'

        filtered_bills = self.get_vat_validation(bills)
        # validar ante el SAT
        if self.sat_validation:
            filtered_bills = self.get_sat_validation(bills)
            # mostrar error si un XML no es válido y detener todo
        self.show_validation_results_to_user(filtered_bills)

        #si no se encontraron productos, mandar error
        if not self.products_valid:
            raise ValidationError(self.products_error_msg)

        # si todos son válidos, extraer datos del XML
        # y crear factura como borrador
        invoice_ids = []
        for bill in bills:
            print('bill: ',bill)
            invoice = bill['invoice_data']
            invoice_line = bill['invoice_line_data']
            version = bill['version']
            #REVISA SI YA EXISTE FACTURA EN SISTEMA
            #DE SER ASI, NO CREA LA FACTURA
            if not self.valdiate_duplicate_invoice(invoice['rfc'],invoice['amount_total'],invoice['date_invoice'],invoice['name']):
                draft = self.create_bill_draft(invoice, invoice_line)
                draft.compute_taxes()
                #se asigna diario
                draft.journal_id = invoice['journal_id']
                draft.account_id = invoice['account_id']

                if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
                    draft.payment_term_id = draft.partner_id.property_payment_term_id
                else:
                    draft.payment_term_id = draft.partner_id.property_supplier_payment_term_id

                # si no se definio termino de pago
                # sumarle 1 dia a la fecha de vencimiento
                if not draft.payment_term_id:
                    #date_due = datetime.strptime(draft.date_invoice, "%Y-%m-%d")
                    date_due = draft.date_invoice
                    date_due = date_due + timedelta(days=1)
                    #print('date_due: ',date_due)
                    draft.date_due = date_due

                #se adjunta xml
                self.attach_to_invoice(draft, bill['xml_file_data'],bill['filename'])
                draft.l10n_mx_edi_cfdi_name = bill['filename']

                #se valida factura
                if draft.type == 'out_invoice':
                    draft.action_invoice_open()
                    draft.l10n_mx_edi_pac_status = 'signed'
                    draft.l10n_mx_edi_sat_status = 'valid'

                #si el termino de pago es contado, se valida la factura y se paga
                # (solo para facturas de venta)
                if self.is_immediate_term(draft.payment_term_id) and draft.type == 'out_invoice':
                # print('----------------------->', invoice['metodo_pago'])
                # if invoice['metodo_pago'] == 'PUE': #pago en una sola exibicion
                    print('se paga invoice')
                    #SE CREA PAGO DE FACTURA
                    payment = self.sudo().create_payment(draft)
                    payment.post()

                invoice_ids.append(draft.id)
        # muestra vista con facturas cargadas
        print("--->invoice_ids: ",invoice_ids)
        return self.action_view_invoices(invoice_ids)


    def create_payment(self, invoice):
        """
        Crea pago para la factura indicada
        """
        AccountRegisterPayments = self.env['account.register.payments']
        payment_type = 'inbound' if invoice.type in ('out_invoice', 'in_refund') else 'outbound'
        if payment_type == 'inbound':
            payment_method = self.env.ref('account.account_payment_method_manual_in')
            #journal_payment_methods = pay_journal.inbound_payment_method_ids
        else:
            payment_method = self.env.ref('account.account_payment_method_manual_out')
            #journal_payment_methods = pay_journal.outbound_payment_method_ids
        #print('self.payment_journal_id.id: ',self.payment_journal_id.id)
        vals = {
            'amount': invoice.amount_total or 0.0,
            'currency_id': invoice.currency_id.id,
            'journal_id': self.payment_journal_id.id,
            'payment_type': payment_type,
            'payment_method_id': payment_method.id,
            'group_invoices': False,
            'invoice_ids': [(6, 0, [invoice.id])],
            'multi': False,
        }
        account_register_payment_id = AccountRegisterPayments.with_context({'active_ids': [invoice.id,]}).create(vals)
        payment_vals = account_register_payment_id.get_payments_vals()

        AccountPayment = self.env['account.payment'].sudo()
        return AccountPayment.create(payment_vals)


    def create_bill_draft(self, invoice, invoice_line):
        """
        sobrescritura de metodo para agregar info nueva
        """
        '''
            Toma la factura y sus conceptos y los guarda
            en Odoo como borrador.
        '''
        
        #print("invoice['type']: ",invoice['type'])
        vals = {
            #'name': name,
            'l10n_mx_edi_cfdi_name': invoice['l10n_mx_edi_cfdi_name'],
            'l10n_mx_edi_cfdi_name2': invoice['l10n_mx_edi_cfdi_name'],
            'journal_id': invoice['journal_id'],
            'team_id': invoice['team_id'],
            'user_id': invoice['user_id'],
            'account_id': invoice['account_id'],
            'warehouse_id': invoice['warehouse_id'],
            'date_invoice': invoice['date_invoice'],
            'account_id': invoice['account_id'],
            'partner_id': invoice['partner_id'],
            'amount_untaxed': invoice['amount_untaxed'],
            'amount_total': invoice['amount_total'],
            'currency_id': invoice['currency_id'],
            'type': invoice['type'],
            'l10n_mx_edi_payment_method_id': invoice['l10n_mx_edi_payment_method_id'],
            'l10n_mx_edi_usage': invoice['l10n_mx_edi_usage'],
            'is_start_amount': True if self.import_type == 'start_amount' else False,
        }

        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            vals['name'] = invoice['name']
        else:
            vals['reference'] = invoice['name']
            vals['create_return'] = False
        
        # How to create and validate Vendor Bills in code? 
        # https://www.odoo.com/forum/ayuda-1/question/131324
        draft = self.env['account.invoice'].create(vals)
        # asignar productos e impuestos a factura
        for product in invoice_line:
            
            uom = False
            if self.import_type != 'start_amount':
                uom = self.get_uom(product.get('sat_uom'))
                if uom:
                    uom = uom[0].id
                else:
                    uom = False

            self.env['account.invoice.line'].create({
                'product_id': product.get('product_id'),
                'invoice_id': draft.id,
                'name': product['name'],
                'quantity': product['quantity'],
                'price_unit': product['price_unit'],
                'account_id': product['account_id'],
                'discount': product.get('discount') or 0.0,
                'price_subtotal': product['price_subtotal'],
                'invoice_line_tax_ids': product.get('taxes'),
                'uom_id': uom,
                'analytic_tag_ids': product['analytic_tag_ids'],
                'account_analytic_id': product['account_analytic_id'],
            })

        return draft

    @api.model
    def is_immediate_term(self, payment_term):
        """
        funcion que indica si un plazo de pago
        es de contado 
        devuelve True/False
        """
        return not any([line.days for line in payment_term.line_ids])


    def get_partner_or_create(self, partner):
        """
        sobrescritura de metodo, los nuevos partner se crearan con
        termino de pago 0 (contado), a menos que se especifique uno distinto
        """
        '''Obtener ID de un partner (proveedor). Si no existe, lo crea.'''
        search_domain = [
            #'|', # obtener por nombre o RFC
            #('name', '=', partner['name']), 
            ('vat', '=', partner['rfc']),
            ('active', '=', True),
        ]

        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            search_domain.append(('customer','=',True))
        else:
            search_domain.append(('supplier','=',True))

        p = self.env['res.partner'].search(search_domain)

        #revisar si es rfc generico
        #indica si se creara un partner generico
        create_generic = False

        if partner['rfc'] in ('XEXX010101000', 'XAXX010101000'):
            for partner_rec in p:
                if partner_rec.name == partner['name']:
                    p = [partner_rec,]
                    break
            else:
                #si no encuentra un match de nombre, crear generico
                create_generic = True


        if not p or create_generic:
            # crear si el proveedor no existe
            payment_term_id = False
            if self.payment_term_id:
                payment_term_id = self.payment_term_id
            else:
                # se obtiene el termino de pago de inmediato
                payment_term_line_id = self.get_payment_term_line(0)
                if payment_term_line_id:
                    payment_term_id = payment_term_line_id.payment_id

            fiscal_position_code = partner.get('position_id')
            fiscal_position = self.env['account.fiscal.position'].search(
                [('l10n_mx_edi_code','=',fiscal_position_code)])
            fiscal_position = fiscal_position and fiscal_position[0]
            fiscal_position_id = fiscal_position.id or False

            vals = {
                'name': partner['name'],
                'vat': partner['rfc'],
                'property_account_position_id': fiscal_position_id,
            }

            if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
                vals['property_payment_term_id'] = payment_term_id and payment_term_id.id or False
                vals['customer'] = True
                vals['supplier'] = False
            else:
                vals['property_supplier_payment_term_id'] = payment_term_id and payment_term_id.id or False
                vals['customer'] = False
                vals['supplier'] = True

            p = self.env['res.partner'].create(vals)
        else:
            p = p[0]

        return p
    
    

    def get_product_or_create(self, product):
        """
        sobrescritura de metodo,
        buscara el nombre del xml en el campo 'custom_name'
        de producto,
        se utilizara un ilike en el dominio
        luego se separara el valor del campo por el limitador '|'
        y se buscara que el nombre sea exacto
        """
        #print('get_product_or_create')
        #primero se busca por nombre
        p = self.env['product.product'].search([
            ('name', '=', product['name'])
        ])
        p = p[0] if p else False
        
        if p:
            return p.id

        #si no se encontro por nombre, se busca por custom_name
        p = self.env['product.product'].search([
            ('custom_name', 'ilike', product['name']),
            ('active', '=', True),
        ])
        
        for rec in p:
            for name in p.custom_name.split('|'):
                if product['name'].lower() == name.strip().lower():
                    return rec.id
        # # si no se encontro ninguno incluir datos de producto en 
        # # mensaje de error
        # self.products_valid = False
        # self.products_error_msg += str(product['name']) + "\n"
        # return False
        
        # crear producto si no existe
        if self.create_product:
            
            EdiCode = self.env["l10n_mx_edi.product.sat.code"]

            product_vals = {
                'name': product['name'],
                'price': product['price_unit'],
                'default_code': product['product_ref'],
                'type': 'product',
            }

            sat_code = EdiCode.search([("code","=",product['sat_product_ref'])])
            # #print("sat_code = ",sat_code)
            if sat_code:
                product_vals["l10n_mx_edi_code_sat_id"] = sat_code[0].id

            uom = self.get_uom(product['sat_uom'])
            # #print(product['sat_uom'])
            # #print("uom = ",uom)
            if uom:
                product_vals["uom_id"] = uom[0].id
                product_vals["uom_po_id"] = uom[0].id

            p = self.env['product.product'].create(product_vals)

        return p.id