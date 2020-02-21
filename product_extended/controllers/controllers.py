# -*- coding: utf-8 -*-
from odoo import http

# class ProductExtended(http.Controller):
#     @http.route('/product_extended/product_extended/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/product_extended/product_extended/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('product_extended.listing', {
#             'root': '/product_extended/product_extended',
#             'objects': http.request.env['product_extended.product_extended'].search([]),
#         })

#     @http.route('/product_extended/product_extended/objects/<model("product_extended.product_extended"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('product_extended.object', {
#             'object': obj
#         })