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
    _name = 'xml.import.wizard'


    import_type = fields.Selection(
        [('start_amount','Saldos Iniciales'),
        ('regular','Factura regular')],
        string='Tipo de Importacion',
        required=True,
        default='start_amount')
    invoice_type = fields.Selection(
        [('out_invoice','Cliente'),
        ('in_invoice','Proveedor')],
        string='Tipo de factura',
        required=True,
        default='out_invoice')
    line_account_id = fields.Many2one('account.account',
        string='Cuenta de linea',
        required=True,
        help='Si la empresa no tiene definida una cuenta de importacion xml por defecto, se usara esta')
    invoice_account_id = fields.Many2one('account.account',
        string='Cuenta de Factura',
        required=True)
    line_analytic_account_id = fields.Many2one('account.analytic.account', 
        string='Cuenta analitica de linea',
        required=False)
    journal_id = fields.Many2one('account.journal',
        string='Diario',
        required=True)
    line_analytic_tag_ids = fields.Many2many('account.analytic.tag', 
        string='Etiquetas analiticas',
        required=False)
    team_id = fields.Many2one('crm.team',
        string='Equipo de ventas',)
    user_id = fields.Many2one('res.users',
        string='Comercial',)
    uploaded_file = fields.Binary(string='Facturas',
        required=True)
    filename = fields.Char(string='Nombre archivo')
    sat_validation = fields.Boolean(string='Validar en SAT',
        default=True)
    create_product = fields.Boolean(string='Crear productos',
        help='Si el producto no se encuentra en Odoo, crearlo automaticamente',
        default=True)
    company_id = fields.Many2one('res.company', 'Company',
        default=lambda self: self.env.user.company_id,
        required=True)
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Plazo de pago',
        help='Se utilizara este plazo de pago para las empresas creadas automaticamente, '+\
        '\n si no se especifica, se usara el de 15 dias'
        )
    description = fields.Char(string='Referencia/Descripcion')


    def check_status_sat(self, obj_xml):
        #print('obj_xml: ',obj_xml)
        try:
            #company = self.get_company_by_current_user()
            company = self.env.user.company_id
            test = company.l10n_mx_edi_pac_test_env
            contract = company.l10n_mx_edi_pac_contract
            password = company.l10n_mx_edi_pac_password
            user = company.l10n_mx_edi_pac_username
            url = 'https://timbrado.pade.mx/odoo/PadeOdooTimbradoService?wsdl'
            rfc_emisor = obj_xml['rfc_emisor']
            #print('rfc_emisor: ',rfc_emisor)
            rfc_receptor = obj_xml['rfc_receptor']
            total = obj_xml['total']
            uuid = obj_xml['uuid']
            client = Client(url, timeout=20)
            if(test):
                num_random = random.randint(1, 6)
                #num_random = 1
                check = client.service.consultarEstatusComprobante(
                    contract, user, password, uuid, rfc_emisor, rfc_receptor, total, ['MODO_PRUEBA:' + str(num_random)])
            else:
                check = client.service.consultarEstatusComprobante(
                   contract, user, password, uuid, rfc_emisor, rfc_receptor, total, [''])
            estado = getattr(check, 'estado', None)
            return estado
        except Exception as e:
            raise UserError(
                "Error al verificar el estatus de la factura: " + str(e))

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

        # si todos son válidos, extraer datos del XML
        # y crear factura como borrador
        invoice_ids = []
        for bill in bills:
            #print('bill: ',bill)
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


                #print('draft: ',draft)
                #print('draft.date_due: ',draft.date_due)
                #se valida factura
                #draft.action_invoice_open()

                #si es factura regular de provedor
                #cargar campo descripcion en name
                if self.import_type == 'regular' and self.invoice_type == 'in_invoice':
                    draft.name = self.description or ''

                #se adjunta xml
                self.attach_to_invoice(draft, bill['xml_file_data'],bill['filename'])
                draft.l10n_mx_edi_cfdi_name = bill['filename']
                invoice_ids.append(draft.id)

        #print('invoice_ids: ',invoice_ids)
        # muestra vista con facturas cargadas
        return self.action_view_invoices(invoice_ids)


    def action_view_invoices(self,invoice_ids):
        self.ensure_one()
        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            view = 'account.action_invoice_tree'
        else:
            view = 'account.action_invoice_tree2'
        action = self.env.ref(view).read()[0]
        action['domain'] = [('id', 'in', invoice_ids)]
        return action       

    def valdiate_duplicate_invoice(self,vat,amount_total,date,invoice_name):
        """
        REVISA SI YA EXISTE LA FACTURA EN SISTEMA
        DEVUELVE TRUE SI YA EXISTE
        FALSE SI NO
        """

        #print('vat: ',vat)
        #print('amount_total: ',amount_total)
        
        #print('invoice_name: ',invoice_name)
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
            #print('DUPLICADA')
            return True
        return False



    def get_raw_file(self):
        '''Convertir archivo binario a byte string.'''
        return base64.b64decode(self.uploaded_file)


    def get_zip_file(self, raw_file):
        '''
            Convertir byte string a archivo zip
            Valida y tira errorsi el archivo subido 
            no era un zip.
        '''
        try:
            # how to parse bytes object into zip file
            # https://stackoverflow.com/q/32910099/            
            zf = zipfile.ZipFile(io.BytesIO(raw_file), 'r')
            return zf
        except zipfile.BadZipFile:
            return False
            #raise ValidationError('Por favor, escoja un archivo ZIP.')


    def get_xml_data(self, file):
        '''
            Ordena datos de archivo xml
        '''
        xmls = []
        # convertir byte string a dict
        xml = xmltodict.parse(file.decode('utf-8'))


        xml_file_data = base64.encodestring(file)

        bill = {
            'filename': self.filename,
            'xml': xml,
            'xml_file_data':xml_file_data,
        }
        xmls.append(bill)
            
        return xmls

    def get_file_ext(self,filename):
        """
        obtiene extencion de archivo, si este lo tiene
        fdevuelve false, si no cuenta con una aextension
        (no es archivo entonces)
        """
        file_ext = filename.split('.')
        if len(file_ext) > 1:
            file_ext = filename.split('.')[1]
            return file_ext
        return False

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
                xml = xmltodict.parse(zip_file.read(fileinfo).decode('utf-8'))


                xml_file_data = base64.encodestring(zip_file.read(fileinfo))
                bill = {
                    'filename': fileinfo.filename,
                    'xml': xml,
                    'xml_file_data':xml_file_data,
                }
                xmls.append(bill)
            
        return xmls


    def check_vat(self,rfc_emisor,rfc_receptor):
        """
        comprueba que el rfc emisor/receptor
        concuerde con la compañia a la que se cargara
        la factura, dependiendo si es de entrada o salida
        regresa True si coincide, False si no
        """
        #print('check_vat')
        #print('self.company_id.vat: ',self.company_id.vat)
        #print('rfc_receptor: ',rfc_receptor)
        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            if self.company_id.vat != rfc_emisor:
                #print('False')
                return False
        else:
            if self.company_id.vat != rfc_receptor:
                #print('False')
                return False
        return True

    def get_vat_validation(self, bills):
        """
        valida que los rfcs coincidan
        con lso registrados en odoo
        regresa bills con datos extra
        """
        #print('get_vat_validation')
        for bill in bills:
            invoice = bill['invoice_data']
            invoice_line = bill['invoice_line_data']
            version = bill['version']
            xml_dict = self.get_vat_dict(bill)
            if not self.check_vat(xml_dict['rfc_emisor'],xml_dict['rfc_receptor']):
                bill['valid'] = False
                bill['state'] = 'RFC no coincide con compañia'

        return bills

    def get_vat_dict(self, bill):
        """
        devuelve diccionario con datos de rfc emisor, receptor
        uuid y total
        """
        self.ensure_one()
        xml_dict = {}
        invoice = bill['invoice_data']
        invoice_line = bill['invoice_line_data']
        version = bill['version']
        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            xml_dict = {
                        'rfc_emisor': invoice['company_rfc'],
                        'rfc_receptor': invoice['rfc'],
                        'total': invoice['amount_total'],
                        'uuid': invoice['uuid'],
                        }
        else:
            xml_dict = {
                        'rfc_emisor': invoice['rfc'],
                        'rfc_receptor': invoice['company_rfc'],
                        'total': invoice['amount_total'],
                        'uuid': invoice['uuid'],
                        }
        return xml_dict


    def get_sat_validation(self, bills):
        """
        valida que factura exista en sat
        y devuelve un diccionario indicadondo
        el estado y si es valida
        """
        #print('get_sat_validation')
        for bill in bills:
            #print('xxxxxxxxxxxxxx')
            #print(bill)
            invoice = bill['invoice_data']
            invoice_line = bill['invoice_line_data']
            version = bill['version']
            xml_dict = self.get_vat_dict(bill)

            state = self.check_status_sat(xml_dict)
            #print('state: ',state)
            bill['valid'] = True
            bill['state'] = state
            if state != 'Vigente':
                bill['valid'] = False
                bill['state'] = state

            # if not self.check_vat(xml_dict['rfc_emisor'],xml_dict['rfc_receptor']):
            #     bill['valid'] = False
            #     bill['state'] = 'RFC no coincide con compañia'
        return bills

    def get_tax_ids(self, tax_group, version='3.3'):
        #print('get_tax_ids: ',tax_group)
        '''
        obtiene los ids de los impuestos
        a partir de nombres de grupos de impuestos
        estructura:
        000|0.16,001|0.0,
        regresa [(6, None, ids)]
        '''
        tax_ids = []
        AccountTax = self.env['account.tax'].sudo()
        
        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            type_tax_use = 'sale'
        else:
            type_tax_use = 'purchase'

        #se elimina ultima ,
        tax_group = tax_group[:-1]
        taxes = tax_group.split(',')
        for tax in taxes:
            #print('tax: ', tax)
            if tax:
                tax_data = tax.split('|')
                tax_number = tax_data[0]
                tax_type = tax_data[2]

                
                domain = [
                    #('tax_code_mx','=',tax_number),
                    #('amount','=',rate),
                    ('type_tax_use','=',type_tax_use),
                    ('company_id','=',self.company_id.id),
                    #('l10n_mx_cfdi_tax_type','=',tax_factor),
                    ]
                tax_factor = False
                if len(tax_data) == 4: #si es 3.3 tendra 4 elementos
                    tax_factor = tax_data[3]
                    domain.append(('l10n_mx_cfdi_tax_type','=',tax_factor))

                if version == '3.3':
                    #3.3
                    if tax_factor != 'Exento':
                        tax_rate = float(tax_data[1])
                        if tax_type == 'tras':
                            rate = (tax_rate*100)
                        else:
                            rate = -(tax_rate*100)
                        domain.append(('amount','=',rate))

                    domain.append(('tax_code_mx','=',tax_number))
                else:
                    #   3.2
                    if tax_data[1] != 'xxx':
                        tax_rate = float(tax_data[1])
                        if tax_type == 'tras':
                            rate = tax_rate
                        else:
                            rate = -(tax_rate)
                        domain.append(('amount','=',rate))
                    domain.append(('name','ilike',tax_number))
                #print('DOMAIN: ',domain)
                tax_id = AccountTax.search(domain)
                if tax_id:
                    tax_id = tax_id[0].id
                    tax_ids.append(tax_id)
        if tax_ids:
            #print('tax_ids: ',tax_ids)
            return [(6, None, tax_ids)]
        return False


    def attach_to_invoice(self, invoice, xml, xml_name):
        """
        adjunta xml a factura
        """
        #print('attach_to_invoice: ',invoice)
        #print('invoice.l10n_mx_edi_cfdi_name: ',invoice.l10n_mx_edi_cfdi_name)
        #PREPARE VALUES
        sub_values = {
            'res_model': 'account.invoice',
            'res_id': invoice.id,
            #'name': invoice.l10n_mx_edi_cfdi_name,
            'name': xml_name,
            'datas': xml,
            'datas_fname': xml_name,
        }
        IrAttachment = self.env['ir.attachment'].sudo()
        attachment = IrAttachment.create(sub_values)
        return attachment

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
                #print('111111: ',root['cfdi:Impuestos'])
                taxes = self.get_cfdi32_taxes(root['cfdi:Impuestos'])
                invoice_line = self.get_cfdi32(root['cfdi:Conceptos']['cfdi:Concepto'], taxes, default_account)
        else:
            # carga de factura regular
            invoice_line = self.add_products_to_invoice(root['cfdi:Conceptos']['cfdi:Concepto'], default_account)

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

        #serie = root.get('@Serie') or root.get('@serie')
        folio = root.get('@Folio') or root.get('@folio')

        invoice['type'] = corrected_invoice_type or self.invoice_type
        #invoice['name'] = serie + ' ' + folio
        invoice['name'] = folio
        invoice['amount_untaxed'] = root.get('@SubTotal') or root.get('@subTotal')
        invoice['amount_total'] = root.get('@Total') or root.get('@total')
        invoice['partner_id'] = partner_id
        invoice['currency_id'] = currency.id
        invoice['date_invoice'] = root.get('@Fecha') or root.get('@fecha')
        #invoice['account_id'] = self.env['account.invoice']._default_journal().id

        ####
        invoice['l10n_mx_edi_cfdi_name'] = filename
        #invoice['l10n_mx_edi_cfdi_name2'] = filename #DENOTA QUE SE CARGO POR MEDIO DE ESTE MODULO
        invoice['journal_id'] = self.journal_id and self.journal_id.id or False
        invoice['team_id'] = self.team_id and self.team_id.id or False
        invoice['user_id'] = self.user_id and self.user_id.id or False
        invoice['account_id'] = self.invoice_account_id.id
        #print('invoice_line: ',invoice_line)
        #OBTENER UUID
        uuid = root['cfdi:Complemento']['tfd:TimbreFiscalDigital'].get('@UUID')
        #print(root['cfdi:Complemento']['tfd:TimbreFiscalDigital'])
        #print('UUID: ',uuid)
        invoice['uuid'] = uuid
        
        invoice['fiscal_position_id'] = partner_rec.property_account_position_id \
                                    and partner_rec.property_account_position_id.id or False

        return invoice, invoice_line, version



    def get_cfdi32_taxes(self,taxes):
        tax_group = ''
        if taxes:
            if float(taxes.get('@totalImpuestosTrasladados',0)) > 0:
                if type(taxes.get('cfdi:Traslados').get('cfdi:Traslado')) == list:
                    for item in taxes.get('cfdi:Traslados').get('cfdi:Traslado'):
                        tax_code = item.get('@impuesto')
                        tax_rate = item.get('@tasa')
                        if tax_code and tax_rate:
                            tax_group = tax_group + tax_code + '|' + tax_rate + '|tras,'
                else:
                    tax_code = taxes['cfdi:Traslados'].get('cfdi:Traslado').get('@impuesto')
                    tax_rate = taxes['cfdi:Traslados'].get('cfdi:Traslado').get('@tasa')
                    if tax_code and tax_rate:
                        tax_group = tax_group + tax_code + '|' + tax_rate + '|tras,'
        return tax_group



    def get_cfdi32(self, products, taxes, default_account):
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
        invoice_line['account_analytic_id'] = self.line_analytic_account_id and self.line_analytic_account_id.id or False
        invoice_line['account_id'] = default_account or self.line_account_id.id
        invoice_line['price_subtotal'] = amount
        invoice_line['price_unit'] = amount
        invoice_line['taxes'] = taxes
        all_products.append(invoice_line)
        return [invoice_line]



    def compact_lines(self, products, default_account):
        '''
          Rebisa las lienas de factura en el xml.
          y crea una sola linea por impuesto
        '''
        all_products = []
        #print('------->products: ',products)
        # asegurarse de que `products` es una lista
        # para poder iterar sobre ella
        if not isinstance(products, list):
            products = [products]
        # se guardan grupos de impuestos
        tax_groups = {}

        # crear un dict para cada producto en los conceptos
        for product in products:
            tax_group = ''
            # si el producto tiene impuestos, obtener datos
            # y asignarselos al concepto
            check_taxes = product.get('cfdi:Impuestos')
            if check_taxes:
                taxes = check_taxes.get('cfdi:Traslados')
                if taxes:
                    #print('type(taxes): ',type(taxes.get('cfdi:Traslado')))
                    if type(taxes.get('cfdi:Traslado')) == list:
                        #print('LISTAA: ',taxes)
                        for item in taxes.get('cfdi:Traslado'):
                            #print('item: ',item)
                            tax_code = item.get('@Impuesto','')
                            tax_rate = item.get('@TasaOCuota','0')
                            tax_factor = item.get('@TipoFactor','')
                            if tax_code:
                                tax_group = tax_group + tax_code + '|' + tax_rate + '|tras|' + tax_factor + ','
                    else:
                        tax_code = taxes.get('cfdi:Traslado').get('@Impuesto','')
                        tax_rate = taxes.get('cfdi:Traslado').get('@TasaOCuota','0')
                        tax_factor = taxes.get('cfdi:Traslado').get('@TipoFactor','')
                        if tax_code:
                            tax_group = tax_group + tax_code + '|' + tax_rate + '|tras|' + tax_factor + ','


                taxes = check_taxes.get('cfdi:Retenciones')
                if taxes:
                    #print('taxes.get(cfdi:Retencion)',taxes.get('cfdi:Retencion'))
                    if type(taxes.get('cfdi:Retencion')) == list:
                        for item in taxes.get('cfdi:Retencion'):
                            #print('item: ',item)
                            tax_code = item.get('@Impuesto','')
                            tax_rate = item.get('@TasaOCuota','0')
                            tax_factor = item.get('@TipoFactor','')
                            if tax_code:
                                tax_group = tax_group + tax_code + '|' + tax_rate + '|ret|' + tax_factor + ','
                    else:
                        tax_code = taxes.get('cfdi:Retencion').get('@Impuesto')
                        tax_rate = taxes.get('cfdi:Retencion').get('@TasaOCuota')
                        tax_factor = taxes.get('cfdi:Retencion').get('@TipoFactor')
                        if tax_code:
                            tax_group = tax_group + tax_code + '|' + tax_rate + '|ret|' + tax_factor + ','

            # se agrega improte acumulado del producto por grupo de impuestos
            #print('--------->tax_groups: ',tax_groups)
            if tax_group in tax_groups:
                #print(float(product.get('@Descuento',0.0)))
                tax_groups[tax_group]['price_subtotal'] += ((float(product['@Importe'])) - float(product.get('@Descuento',0.0)))
            else:
                #print(float(product.get('@Descuento',0.0)))
                tax_groups[tax_group] = {}
                tax_groups[tax_group]['price_subtotal'] = ((float(product['@Importe'])) - float(product.get('@Descuento',0.0)))

            # agregar concepto a la lista de conceptos
            #all_products.append(invoice_line)

        # se crean las lineas por cada grupo de impuestos
        for group in tax_groups:
            #print('group: ',group)
            taxes = self.get_tax_ids(group)
            invoice_line = {}
            invoice_line['name'] = 'SALDOS INICIALES'
            invoice_line['quantity'] = 1

            analytic_tag_ids = False
            if self.line_analytic_tag_ids:
                analytic_tag_ids = [(6, None, self.line_analytic_tag_ids.ids)]

            invoice_line['analytic_tag_ids'] = analytic_tag_ids
            invoice_line['account_analytic_id'] = self.line_analytic_account_id and self.line_analytic_account_id.id or False
            invoice_line['account_id'] = default_account or self.line_account_id.id
            invoice_line['price_subtotal'] = tax_groups[group]['price_subtotal']
            invoice_line['price_unit'] = tax_groups[group]['price_subtotal']
            invoice_line['taxes'] = taxes
            all_products.append(invoice_line)

        return all_products


    def add_products_to_invoice(self, products, default_account):
        '''
            Obtener datos de los productos (Conceptos).
        '''
        all_products = []

        # asegurarse de que `products` es una lista
        # para poder iterar sobre ella
        if not isinstance(products, list):
            products = [products]

        # crear un dict para cada producto en los conceptos
        for product in products:
            # datos básicos
            invoice_line = {}
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
            invoice_line['account_analytic_id'] = self.line_analytic_account_id and self.line_analytic_account_id.id or False
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
                        #traslado['amount'] = element.get('@Importe') or element.get('@importe')
                        #traslado['base'] = element.get('@Base')
                        #traslado['account_id'] = 19
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
                        tax_factor = element.get('@TipoFactor','')
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
        
        return all_products


    def create_bill_draft(self, invoice, invoice_line):
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
            'amount_total': invoice['amount_total'],
            'currency_id': invoice['currency_id'],
            'type': invoice['type'],
            'is_start_amount': True if self.import_type == 'start_amount' else False,
        }

        if self.invoice_type == 'out_invoice' or self.invoice_type == 'out_refund':
            vals['name'] = invoice['name']
        else:
            vals['reference'] = invoice['name']
        
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

    
    def get_payment_term_line(self, days):
        '''
        obtiene linea de termino de pago indicado,
        se podra accedfer al termino de pago desde el campo payment_id
        days: in que representa el no. de dias del t. de pago a buscar
        '''
        payment_term_line_id = False
        PaymentTermLine = self.env['account.payment.term.line']
        domain = [('days','=',days),('payment_id.company_id','=',self.company_id.id)]
        #print('domain: ',domain)
        payment_term_line_id = PaymentTermLine.search(domain)
        if payment_term_line_id:
            #print('payment_term_line_id')
            payment_term_line_id = payment_term_line_id[0]
        return payment_term_line_id

    
    def get_partner_or_create(self, partner):
        '''Obtener ID de un partner (proveedor). Si no existe, lo crea.'''
        search_domain = [
            #'|', # obtener por nombre o RFC
            #('name', '=', partner['name']), 
            ('vat', '=', partner['rfc'])
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
                    #print('partner.name: ',partner_rec.name)
                    #print("partner['name']: ",partner['name'])
                    #print('NO SE CREA GENERICO')
                    break
            else:
                #print('SE CREA GENERICO')
                #si no encuentra un match de nombre, crear generico
                create_generic = True


        if not p or create_generic:
            # crear si el proveedor no existe

            if self.payment_term_id:
                payment_term_id = self.payment_term_id
            else:
                # se obtiene el termino de pago de 15 dias
                payment_term_line_id = self.get_payment_term_line(15)
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
                vals['property_payment_term_id'] = payment_term_id.id
                vals['customer'] = True
                vals['supplier'] = False
            else:
                vals['property_supplier_payment_term_id'] = payment_term_id.id
                vals['customer'] = False
                vals['supplier'] = True

            p = self.env['res.partner'].create(vals)
        else:
            p = p[0]

        return p


    def get_uom(self, sat_code):
        """
        obtiene record de unidad de medida
        sat_code: string con el codigo del sat de la unidad de medida
        """
        ProductUom = self.env["uom.uom"]
        return ProductUom.search([("l10n_mx_edi_code_sat_id.code", "=", sat_code)])


    def get_product_or_create(self, product):
        '''Obtener ID de un producto. Si no existe, lo crea.'''
        #print('get_product_or_create')
        p = self.env['product.product'].search([
            ('name', '=', product['name'])
        ])
        p = p[0] if p else False
        #print('p: ',p)
        if not p and self.create_product:
            # crear producto si no existe
            EdiCode = self.env["l10n_mx_edi.product.sat.code"]

            product_vals = {
                'name': product['name'],
                'price': product['price_unit'],
                'default_code': product['product_ref'],
                'type': 'product',
            }

            sat_code = EdiCode.search([("code","=",product['sat_product_ref'])])
            #print("sat_code = ",sat_code)
            if sat_code:
                product_vals["l10n_mx_edi_code_sat_id"] = sat_code[0].id

            uom = self.get_uom(product['sat_uom'])
            #print(product['sat_uom'])
            #print("uom = ",uom)
            if uom:
                product_vals["uom_id"] = uom[0].id
                product_vals["uom_po_id"] = uom[0].id

            p = self.env['product.product'].create(product_vals)
        # if not p:
        #     raise UserError("No se encontro el un producto con nombre '{}'".format(product['name']))
        if not p:
            return False
        return p.id


    def add_product_tax(self, invoice_id, vals):
        '''Agregar impuestos correspondientes a una factura y sus conceptos.'''

        for tax in vals['taxes']:
            tax_id = tax['tax_id'][1]
            # aun no se que hacer con las retenciones
            # se tienen que restar al monto total
            # y no se si agregarlas a la lista de impuestos
            # que aparece en la factura en Odoo
            if tax_id == 6:
                continue

            tax_name = self.env['account.tax'].search([('id', '=', tax_id)]).name
            self.env['account.invoice.tax'].create({
                'invoice_id': invoice_id,
                'name': tax_name,
                'tax_id': tax_id,
                'account_id': tax['account_id'], 
                'amount': tax['amount'],
                'base': tax['base'],
            })


    def get_discount_percentage(self, product):
        '''Calcular descuento de un producto en porcentaje.'''
        
        d = (float(product['@Descuento']) / float(product['@Importe'])) * 100
        return d

    def show_validation_results_to_user(self, bills):
        '''
            Checar si los XMLs subidos son válidos.
            Mostrar error al usuario si no, y detener proceso.
        '''

        # check a value in list of dicts
        # https://stackoverflow.com/q/3897499/
        if any(d['valid'] == False for d in bills):
            #not_valid_idx = self.find(bills, 'valid', False)
            #not_valid = [bills[i] for i in not_valid_idx]
            not_valid = [bill for bill in bills if not bill.get('valid')]

            msg = 'Los siguientes archivos no son válidos:\n'
            for bill in not_valid:
                msg += bill['filename'] + ' - ' + bill['state']+'\n'
            #msg += 'Si aun asi desea cargar estos xml, desmarque la casilla "Validar en SAT"'
            raise ValidationError(msg)
        else:
            return True