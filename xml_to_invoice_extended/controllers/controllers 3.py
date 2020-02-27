# -*- coding: utf-8 -*-
from odoo import http

# class XmlToInvoiceExtended(http.Controller):
#     @http.route('/xml_to_invoice_extended/xml_to_invoice_extended/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/xml_to_invoice_extended/xml_to_invoice_extended/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('xml_to_invoice_extended.listing', {
#             'root': '/xml_to_invoice_extended/xml_to_invoice_extended',
#             'objects': http.request.env['xml_to_invoice_extended.xml_to_invoice_extended'].search([]),
#         })

#     @http.route('/xml_to_invoice_extended/xml_to_invoice_extended/objects/<model("xml_to_invoice_extended.xml_to_invoice_extended"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('xml_to_invoice_extended.object', {
#             'object': obj
#         })