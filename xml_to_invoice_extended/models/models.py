# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError,UserError
from datetime import datetime, timedelta
#from xml.sax.saxutils import escape

import xmltodict

import base64
import zipfile
import io
import calendar

from suds.client import Client
import random
import pdb


class XmlImportWizard(models.TransientModel):
    _inherit = 'xml.import.wizard'
    
    sat_validation = fields.Boolean(string='Validar en SAT',
        default=False)
    invoice_type = fields.Selection(
        [('out_invoice','Cliente'),
        ('in_invoice','Proveedor')],
        string='Tipo de factura',
        required=False,
        default=False)
    line_account_id = fields.Many2one('account.account',
        string='Cuenta de linea',
        required=False,
        help='Si la empresa no tiene definida una cuenta de importacion xml por defecto, se usara esta')
    invoice_account_id = fields.Many2one('account.account',
        string='Cuenta de Factura',
        required=False)
    journal_id = fields.Many2one('account.journal',
        string='Diario',
        required=False)
    payment_journal_id = fields.Many2one('account.journal',
        string='Banco de pago', required=False, domain="[('type','=','bank')]")
    
    ### Cliente ##########################################
    cuenta_cobrar_cliente_id = fields.Many2one('account.account',
        string='Cuenta por Cobrar Clientes',
        required=True, default=lambda self: self.env['account.account'].search([('code','=','105.01.01'),('company_id','=',self.env.user.company_id.id)]))
    cuenta_ingreso_cliente_id = fields.Many2one('account.account',
        string='Cuenta de Ingresos Clientes',
        required=True, default=lambda self: self.env['account.account'].search([('code','=','401.01.01'),('company_id','=',self.env.user.company_id.id)]))
    line_analytic_account_customer_id = fields.Many2one('account.analytic.account', 
        string='Cuenta analitica de linea',
        required=False)
    payment_term_customer_id = fields.Many2one(
        'account.payment.term',
        string='Plazo de pago',
        help='Se utilizara este plazo de pago para las empresas creadas automaticamente, '+\
        '\n si no se especifica, se usara el de 15 dias'
        )
    user_customer_id = fields.Many2one('res.users',
        string='Representante Comercial', required=True)
    team_customer_id = fields.Many2one('crm.team',
        string='Equipo de ventas', required=True)
    warehouse_customer_id = fields.Many2one('stock.warehouse', string='Almacén',
        help='Necesario para crear el mov. de almacén', required=True)
    journal_customer_id = fields.Many2one('account.journal',
        string='Diario Clientes',
        required=True, default=lambda self: self.env['account.journal'].search([('name','=','CLIENTES - Facturas'),('company_id','=',self.env.user.company_id.id)]))
    payment_journal_customer_id = fields.Many2one('account.journal',
        string='Banco de pago', domain="[('type','=','bank')]")
    line_analytic_tag_customer_ids = fields.Many2many('account.analytic.tag', 
        string='Etiquetas analíticas',
        required=False)
    invoice_status_customer = fields.Selection([('draft','Borrador'),('abierta','Abierta'),('pagada','Pagada')], string='Subir en estatus')
    invoice_payment_type_customer = fields.Selection([('fecha_factura','Con  la misma fecha de la factura'),('fecha_fin_mes','Con la fecha de final del mes'),('fecha_especifica','Con alguna fecha específica')], string='Fecha de pago')
    invoice_date_customer = fields.Date(string='Fecha')
    ### ¿Banco?
    
    ### Proveedor #############################
    cuenta_pagar_proveedor_id = fields.Many2one('account.account',
        string='Cuenta por Pagar Proveedores',
        required=True, default=lambda self: self.env['account.account'].search([('code','=','201.01.01'),('company_id','=',self.env.user.company_id.id)]))
    cuenta_gasto_proveedor_id = fields.Many2one('account.account',
        string='Cuenta de Gastos de Proveedor',
        required=True, default=lambda self: self.env['account.account'].search([('code','=','601.84.01'),('company_id','=',self.env.user.company_id.id)]))
    line_analytic_account_provider_id = fields.Many2one('account.analytic.account', 
        string='Etiquetas analíticas', required=False)
    payment_term_provider_id = fields.Many2one(
        'account.payment.term',
        string='Plazo de pago',
        help='Se utilizara este plazo de pago para las empresas creadas automaticamente, '+\
        '\n si no se especifica, se usara el de 15 dias'
        )
    user_provider_id = fields.Many2one('res.users',
        string='Comprador',)
    warehouse_provider_id = fields.Many2one('stock.warehouse', string='Almacén', 
        help='Necesario para crear el mov. de almacén', required=False)
    journal_provider_id = fields.Many2one('account.journal',
        string='Diario Proveedores',
        required=True, default=lambda self: self.env['account.journal'].search([('name','=','PROVEEDORES - Facturas'),('company_id','=',self.env.user.company_id.id)]))
    payment_journal_provider_id = fields.Many2one('account.journal',
        string='Banco de pago', domain="[('type','=','bank')]")
    line_analytic_tag_provider_ids = fields.Many2many('account.analytic.tag', 
        string='Etiquetas analíticas',
        required=False)
    invoice_status_provider = fields.Selection([('draft','Borrador'),('abierta','Abierta'),('pagada','Pagada')], string='Subir en estatus', required=False)
    invoice_payment_type_provider = fields.Selection([('fecha_factura','Con  la misma fecha de la factura'),('fecha_fin_mes','Con la fecha de final del mes'),('fecha_especifica','Con alguna fecha específica')], string='Fecha de pago')
    invoice_date_provider = fields.Date(string='Fecha')
    ##############################
    
    @api.onchange('invoice_status_customer')
    def _onchange_invoice_status_customer(self):
        if not self.invoice_status_customer:
            self.invoice_payment_type_customer = False
            self.invoice_date_provider = False
    
    @api.onchange('invoice_type','company_id')
    def _onchange_invoice_type(self):
        pass
        
        
    @api.onchange('uploaded_file')
    def onchnage_uploaded_file(self):
        if self.uploaded_file:
            file_ext = self.get_file_ext(self.filename)
            if file_ext.lower() not in ('xml','zip'):
                raise ValidationError('Por favor, escoja un archivo ZIP o XML')
            if file_ext.lower() == 'xml':
                raw_file = self.get_raw_file()
                bills = self.get_xml_data(raw_file)
                root = bills[0]['xml']['cfdi:Comprobante']
                vendor = root['cfdi:Receptor']
                vendor2 = root['cfdi:Emisor']
                rfc_receptor = vendor.get('@Rfc') or vendor.get('@rfc')
                rfc_emisor = vendor2.get('@Rfc') or vendor2.get('@rfc')
                #tipo_factura = self.validate_invoice_type(rfc_emisor, rfc_receptor)
                #raise ValidationError(tipo_factura)
                self.validate_invoice_type(rfc_emisor, rfc_receptor)
            else:
                self.invoice_type = False
        else:
            self.invoice_type = False
    
    def validate_invoice_type(self, rfc_emisor, rfc_receptor):
        emisor_company_id = self.env['res.company'].search([('vat','=',rfc_emisor)])
        flag = True
        invoice_type = ''
        if self.company_id == emisor_company_id:
            invoice_type = 'out_invoice'
            self.invoice_type = 'out_invoice'
            flag = False
            #return 'cliente'
        receptor_company_id = self.env['res.company'].search([('vat','=',rfc_receptor)])
        if self.company_id == receptor_company_id:
            invoice_type = 'in_invoice'
            self.invoice_type = 'in_invoice'
            flag = False
            #return 'proveedor'
        if flag:
            invoice_type = 'invalid_invoice'
            return invoice_type
            #raise ValidationError('La factura no corresponde a la compañía actual.')
        else:
            return invoice_type

        
    def get_xml_data(self, file):
        '''
            Ordena datos de archivo xml
        '''
        xmls = []
        # convertir byte string a dict
        xml_string = file.decode('utf-8')
        xml_string = self.clean_xml(xml_string)
        xml = xmltodict.parse(xml_string)
        

        xml_file_data = base64.encodestring(file)
        
        #raise ValidationError(self.filename)

        bill = {
            'filename': self.filename,
            'xml': xml,
            'xml_file_data':xml_file_data,
        }
        xmls.append(bill)
            
        return xmls

    def get_xml_from_zip(self, zip_file):
        '''
            Extraer archivos del .zip.
            Convertir XMLs a diccionario para 
            un manejo mas fácil de los datos.
        '''
        xmls = []
        for fileinfo in zip_file.infolist():
            #print(fileinfo.filename)
            file_ext = self.get_file_ext(fileinfo.filename)
            if file_ext in ('xml','XML'):
                #print('entro')
                # convertir byte string a dict
                xml_string = zip_file.read(fileinfo).decode('utf-8')
                xml_string = self.clean_xml(xml_string)
                xml = xmltodict.parse(xml_string)


                xml_file_data = base64.encodestring(zip_file.read(fileinfo))
                bill = {
                    'filename': fileinfo.filename,
                    'xml': xml,
                    'xml_file_data':xml_file_data,
                }
                xmls.append(bill)
            
        return xmls
    
    def clean_xml(self, xml_string):
        # Este método sirve para remover los caracteres que, en algunos XML, vienen al inicio del string antes del primer 
        # caracter '<'
        new_ml_string = xml_string.split('<')
        to_remove = new_ml_string[0]
        #raise ValidationError(to_remove)
        new_ml_string = xml_string.replace(to_remove, '')
        #new_ml_string = new_ml_string.replace('&#xA;',' ')
        #new_ml_string = new_ml_string.replace('&quot;','"')
        
        return new_ml_string

    @api.multi
    def validate_bills(self):
        '''
            Función principal. Controla todo el flujo de 
            importación al clickear el botón (parsea el archivo
            subido, lo valida, obtener datos de la factura y
            guardarla crea factura en estado de borrador).
        ''' 
        # parsear archivo subido (bye string => .zip)
        #file_ext = self.filename.split('.')[1]
        
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

        for bill in bills:
            #print('bill: ',bill)
            invoice, invoice_line, version, invoice_type, bank_id = self.prepare_invoice_data(bill)
            
            #if invoice_type != 'invalid_invoice':
            bill['invoice_type'] = invoice_type
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

        # si todos son válidos, extraer datos del XML
        # y crear factura como borrador
        invoice_ids = []
        invoices_no_created = []
        for bill in bills:
            #print('bill: ',bill)
            invoice = bill['invoice_data']
            invoice_line = bill['invoice_line_data']
            version = bill['version']
            #REVISA SI YA EXISTE FACTURA EN SISTEMA
            #DE SER ASI, NO CREA LA FACTURA
            if bill['invoice_type'] != 'invalid_invoice':
                if not self.valdiate_duplicate_invoice(invoice['rfc'],invoice['amount_total'],invoice['date_invoice'],invoice['name']):
                    draft = self.create_bill_draft(invoice, invoice_line, invoice_type)
                    #raise ValidationError(draft.journal_id)
                    draft.compute_taxes()
                    #raise ValidationError(draft.tax_line_ids[0].amount)
                    draft.tax_line_ids[0].amount = invoice['amount_tax']
                    #raise ValidationError(draft.tax_line_ids[0].amount)
                    #se asigna diario
                    draft.journal_id = invoice['journal_id']
                    draft.account_id = invoice['account_id']

                    if invoice_type == 'out_invoice' or invoice_type == 'out_refund':
                        draft.payment_term_id = draft.partner_id.property_payment_term_id
                    else:
                        draft.payment_term_id = draft.partner_id.property_supplier_payment_term_id


                    #print('draft: ',draft)
                    #print('draft.date_due: ',draft.date_due)
                    #se valida factura
                    #draft.action_invoice_open()

                    #si es factura regular de provedor
                    #cargar campo descripcion en name
                    if self.import_type == 'regular' and invoice_type == 'in_invoice':
                        draft.name = self.description or ''

                    #se adjunta xml
                    self.attach_to_invoice(draft, bill['xml_file_data'],bill['filename'])
                    draft.l10n_mx_edi_cfdi_name = bill['filename']
                    
                    ### Abierta factura proveedor
                    if self.invoice_status_provider == 'abierta':
                        #se valida factura
                        #draft.action_invoice_open()
                        #if draft.type == 'out_invoice':
                        draft.action_invoice_open()
                        draft.l10n_mx_edi_pac_status = 'signed'
                        draft.l10n_mx_edi_sat_status = 'valid'
                    ### Paga factura proveedor
                    if self.invoice_status_provider == 'pagada':
                        draft.action_invoice_open()
                        draft.l10n_mx_edi_pac_status = 'signed'
                        draft.l10n_mx_edi_sat_status = 'valid'
                        
                        if self.invoice_payment_type_provider == 'fecha_fin_mes':
                            year = datetime.now().year
                            month = datetime.now().month
                            day = calendar.monthrange(year, month)[1]
                            draft.date_invoice = datetime(year, month, day).date()
                        if self.invoice_payment_type_provider == 'fecha_especifica':
                            if not draft.date_invoice < self.invoice_date_provider:
                                draft.date_invoice = self.invoice_date_provider
                        
                        payment = self.sudo().create_payment(draft, bank_id)
                            #raise ValidationError('payment')
                        payment.post()
                                
                    ### Abierta factura cliente
                    if self.invoice_status_customer == 'abierta':
                        #se valida factura
                        #draft.action_invoice_open()
                        #if draft.type == 'out_invoice':
                        draft.action_invoice_open()
                        draft.l10n_mx_edi_pac_status = 'signed'
                        draft.l10n_mx_edi_sat_status = 'valid'
                    
                    ### Paga factura cliente
                    if self.invoice_status_customer == 'pagada':
                        if draft.type == 'out_invoice':
                            draft.action_invoice_open()
                            draft.l10n_mx_edi_pac_status = 'signed'
                            draft.l10n_mx_edi_sat_status = 'valid'
                        if self.invoice_payment_type_customer == 'fecha_fin_mes':
                            year = datetime.now().year
                            month = datetime.now().month
                            day = calendar.monthrange(year, month)[1]
                            draft.date_invoice = datetime(year, month, day).date()
                        if self.invoice_payment_type_customer == 'fecha_especifica':
                            if not draft.date_invoice < self.invoice_date_customer:
                                draft.date_invoice = self.invoice_date_customer
                        #si el termino de pago es contado, se valida la factura y se paga
                        # (solo para facturas de venta)
                        if self.is_immediate_term(draft.payment_term_id) and draft.type == 'out_invoice':
                        # print('----------------------->', invoice['metodo_pago'])
                        # if invoice['metodo_pago'] == 'PUE': #pago en una sola exibicion
                            #raise ValidationError('ok')
                            #SE CREA PAGO DE FACTURA
                            #raise ValidationError(bank_id)
                            #raise ValidationError(invoice_type)
                            payment = self.sudo().create_payment(draft, bank_id)
                            #raise ValidationError('payment')
                            payment.post()
                    # si no se definio termino de pago
                    # sumarle 1 dia a la fecha de vencimiento
                    if not draft.payment_term_id:
                        #date_due = datetime.strptime(draft.date_invoice, "%Y-%m-%d")
                        date_due = draft.date_invoice
                        date_due = date_due + timedelta(days=1)
                        #print('date_due: ',date_due)
                        draft.date_due = date_due
                    invoice_ids.append(draft.id)
                else:
                    invoices_no_created.append(invoice['name'])
            else:
                invoices_no_created.append(invoice['name'])
        #raise ValidationError(len(invoices_no_created))
        if len(invoices_no_created) > 0:
            invoice_names = ', '.join(invoices_no_created)
            
            mensaje = "Las siguientes facturas con número de folio/serie/certificado no fueron cargadas porque ya existen o porque pertenecen a otra compañía: %s" % invoice_names
            if len(invoices_no_created) == 1:
                mensaje = "La siguiente factura con número de folio/serie/certificado no fue cargada porque ya existe: %s" % invoice_names
            view = self.env.ref('xml_to_invoice_extended.sh_message_wizard')
            view_id = view and view.id or False
            context = dict(self._context or {})
            context['message'] = mensaje
            
            return {
                'name': 'Advertencia',
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'sh.message.wizard',
                'views': [(view.id, 'form')],
                'view_id': view.id,
                'target': 'new',
                'context': context
            }
            #raise ValidationError("Las siguientes facturas no fueron cargadas porque ya existen: %s" % invoice_names)

        #print('invoice_ids: ',invoice_ids)
        # muestra vista con facturas cargadas
       # raise ValidationError('Terminó')
        return self.action_view_invoices(invoice_ids)
    
    def get_uom(self, sat_code):
        """
        obtiene record de unidad de medida
        sat_code: string con el codigo del sat de la unidad de medida
        """
        ProductUom = self.env["uom.uom"]
        if sat_code == 'C62':
            return ProductUom.search([("l10n_mx_edi_code_sat_id.code", "=", 'H87')])
        return ProductUom.search([("l10n_mx_edi_code_sat_id.code", "=", sat_code)])

    
    def create_payment(self, invoice, bank_id):
        
        """
        Crea pago para la factura indicada
        """
        AccountRegisterPayments = self.env['account.register.payments'].sudo()
        if invoice.type == 'out_invoice':
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
                'journal_id': bank_id,
                'payment_type': payment_type,
                'payment_method_id': payment_method.id,
                'group_invoices': False,
                'invoice_ids': [(6, 0, [invoice.id])],
                'multi': False,
            }
        if invoice.type == 'in_invoice':
            #raise ValidationError(payment_type)
            vals = {
                'amount': invoice.amount_total or 0.0,
                'currency_id': invoice.currency_id.id,
                'journal_id': bank_id,
                'payment_type': False,
                'payment_method_id': False,
                'group_invoices': False,
                'invoice_ids': [(6, 0, [invoice.id])],
                'multi': False,
            }
        account_register_payment_id = AccountRegisterPayments.with_context({'active_ids': [invoice.id,]}).create(vals)
        payment_vals = account_register_payment_id.get_payments_vals()

        AccountPayment = self.env['account.payment'].sudo()
        return AccountPayment.create(payment_vals)

    
    def add_products_to_invoice(self, products, default_account, account_analytic_id, invoice_type):
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
            # A. Marquez 28/12/19: Para obtener el valor unitario "correcto"
            cantidad = float(invoice_line['quantity'])
            importe = float(invoice_line['price_subtotal'])
            valor_unitario = str(importe/cantidad)
            ###
            #invoice_line['price_unit'] = product.get('@ValorUnitario') or product.get('@valorUnitario')
            invoice_line['price_unit'] = valor_unitario
            #datos para creacion de producto
            invoice_line['sat_product_ref'] = product.get('@ClaveProdServ') or product.get('@claveProdServ')
            invoice_line['product_ref'] = product.get('@NoIdentificacion') or product.get('@noIdentificacion')
            invoice_line['sat_uom'] = product.get('@ClaveUnidad') or product.get('@claveUnidad')

            analytic_tag_ids = False
            if invoice_type == 'out_invoice':
                if self.line_analytic_tag_customer_ids:
                    analytic_tag_ids = [(6, None, self.line_analytic_tag_customer_ids.ids)]
            else:
                if self.line_analytic_tag_provider_ids:
                    analytic_tag_ids = [(6, None, self.line_analytic_tag_provider_ids.ids)]

            invoice_line['analytic_tag_ids'] = analytic_tag_ids
            invoice_line['account_analytic_id'] = account_analytic_id
            if invoice_type == 'out_invoice':
                invoice_line['account_id'] = default_account or self.cuenta_ingreso_cliente_id.id
            else:
                invoice_line['account_id'] = default_account or self.cuenta_gasto_proveedor_id.id

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
                        #raise ValidationError(tax_group)
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
    
    
    def create_bill_draft(self, invoice, invoice_line, invoice_type):
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

            'date_invoice': invoice['date_invoice'],
            'account_id': invoice['account_id'],
            'partner_id': invoice['partner_id'],
            'amount_untaxed': invoice['amount_untaxed'],
            #'amount_tax': invoice['amount_tax'],
            'amount_total': invoice['amount_total'],
            'currency_id': invoice['currency_id'],
            'type': invoice['type'],
            'warehouse_id': invoice['warehouse_id'],
            'is_start_amount': True if self.import_type == 'start_amount' else False,
        }

        if invoice_type == 'out_invoice' or invoice_type == 'out_refund':
            vals['name'] = invoice['name']
        else:
            vals['reference'] = invoice['name']
        
        # How to create and validate Vendor Bills in code? 
        # https://www.odoo.com/forum/ayuda-1/question/131324
        draft = self.env['account.invoice'].create(vals)
        # asignar productos e impuestos a factura
        for product in invoice_line:
            #if product['price_subtotal'] == '3.02':
            #    raise ValidationError(product['price_subtotal'], 'ok')
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
        vendor = root['cfdi:Receptor']
        vendor2 = root['cfdi:Emisor']
        rfc_receptor = vendor.get('@Rfc') or vendor.get('@rfc')
        rfc_emisor = vendor2.get('@Rfc') or vendor2.get('@rfc')
        
        invoice_type = self.validate_invoice_type(rfc_emisor, rfc_receptor)
        
        #if invoice_type == 'invalid_invoice':
        #    return invoice, invoice_line, version, invoice_type
        #raise ValidationError(invoice_type)
        if invoice_type == 'out_invoice' or invoice_type == 'out_refund':
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
        no_certificado = root.get('@NoCertificado') or root.get('@nocertificado')
        metodopago = root.get('@MetodoPago') or root.get('@metodoPago') or False
        forma_pago = root.get('@FormaPago') or root.get('@formaPago')
        uso_cfdi = root['cfdi:Receptor'].get('@UsoCFDI') or root['cfdi:Receptor'].get('@usoCFDI')

        journal_id, analytic_account_id, warehouse_id, bank_id =self.get_company_xml_import_data(invoice_type, serie)
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
            invoice_line = self.add_products_to_invoice(root['cfdi:Conceptos']['cfdi:Concepto'], default_account, analytic_account_id, invoice_type)

        # obtener datos de proveedor
        # crear al proveedor si no existe
        # #print('VENDOR: ',vendor.get('@Nombre'))
        # #print('VENDOR: ',vendor.get('@nombre'))
        tipo_comprobante = root.get('@TipoDeComprobante') or root.get('@tipoDeComprobante')
        #raise ValidationError(tipo_comprobante)
        invoice['tipo_comprobante'] = tipo_comprobante
        #SE CORRIGE TIPO SEGUN EL TIPO DE COMPROBANTE
        # SOLO TOMA EN CUENTA INGRESOS Y EGRESOS
        #print('tipo_comprobante: ',tipo_comprobante)
        corrected_invoice_type = False
        if tipo_comprobante.upper() == 'E':
            if invoice_type == 'out_invoice':
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

        invoice['type'] = corrected_invoice_type or invoice_type

        invoice['name'] = folio
        if serie:
            invoice['name'] = serie + ' ' + folio
        if not folio:
            invoice['name'] = no_certificado

        invoice['amount_untaxed'] = root.get('@SubTotal') or root.get('@subTotal')
        invoice['amount_tax'] = root['cfdi:Impuestos']['cfdi:Traslados']['cfdi:Traslado'].get('@Importe')
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
        if invoice_type == 'out_invoice':
            invoice['account_id'] = self.cuenta_cobrar_cliente_id.id
        else:
            invoice['account_id'] = self.cuenta_pagar_proveedor_id.id
        #print('invoice_line: ',invoice_line)
        #OBTENER UUID
        uuid = root['cfdi:Complemento']['tfd:TimbreFiscalDigital'].get('@UUID')
        #print(root['cfdi:Complemento']['tfd:TimbreFiscalDigital'])
        #print('UUID: ',uuid)
        invoice['uuid'] = uuid
        return invoice, invoice_line, version, invoice_type, bank_id

    def get_company_xml_import_data(self, invoice_type, serie=False):
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
        if invoice_type == 'out_invoice':
            if not serie:
                raise ValidationError('El xml no contiene el atributo serie')
            x = 0
            for line in self.company_id.xml_import_line_ids:
                if x == 2:
                    pass
                    #raise ValidationError(str(line.xml_import_journal_id.sequence_id.name) + ' - '+ str(serie))
                x += 1
                if line.xml_import_journal_id.sequence_id.name == serie:
                    journal_id = line.xml_import_journal_id.id
                    analytic_account_id = line.xml_import_analytic_account_id.id
                    warehouse_id = line.xml_import_warehouse_id.id
                    bank_id = line.xml_import_bank_id.id
                    break
            # for journal in self.company_id.xml_import_journal_ids:
            #     if journal.sequence_id.name == serie:
            #         journal_id = journal.id
            #         break
            else:
                raise ValidationError('No se encontro un diario configurado con la serie {} en la compañia seleccionada\nPor favor configure uno!'.format(serie))
        else:
            #if invoice_type == 'out_invoice':
            #    journal_id = self.journal_customer_id.id
            #    analytic_account_id = self.line_analytic_account_customer_id.id
            #    warehouse_id = self.warehouse_customer_id and self.warehouse_customer_id.id or False
            #else:
            journal_id = self.journal_provider_id.id
            analytic_account_id = self.line_analytic_account_provider_id.id
            warehouse_id = self.warehouse_provider_id and self.warehouse_provider_id.id or False
            bank_id = self.payment_journal_provider_id.id
        return journal_id, analytic_account_id, warehouse_id, bank_id
