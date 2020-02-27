# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError, RedirectWarning, UserError

class product_extended(models.Model):
    _inherit = 'product.template'
    
    public_categ_ids = fields.Many2many('product.public.category', string='Website Product Category',
                                        help="The product will be available in each mentioned e-commerce category. Go to"
                                        "Shop > Customize and enable 'E-commerce categories' to view all e-commerce categories.", compute="compute_categ", readonly=True, store=True)
    
    @api.depends('categ_id')
    def compute_categ(self):
        if self.categ_id:
            prod_cat = self.env['product.public.category']
            categ = prod_cat.search([('name','=',self.categ_id.name)])
            if not categ:
                new_prod_cat = prod_cat.create({'name': self.categ_id.name})
                self.public_categ_ids = new_prod_cat
            else:
                self.public_categ_ids = categ
    
    @api.multi
    def process_categs(self):
        products = self.env['product.template'].search([])
        for p in products:
            if p.categ_id:
                prod_cat = self.env['product.public.category']
                categ = prod_cat.search([('name','=',p.categ_id.name)])
                if not categ:
                    new_prod_cat = prod_cat.create({'name': p.categ_id.name})
                    p.public_categ_ids = new_prod_cat
                else:
                    p.public_categ_ids = categ
        