# -*- coding: utf-8 -*-
from odoo import api, models, fields


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = "Website Product Brand"
    _rec_name = 'name'
    _order = "sequence, name"

    name = fields.Char(string='Brand Name', required=True)
    sequence = fields.Integer()
    image = fields.Binary(string="Image")
    description = fields.Text(string='Brand Description')
    product_ids = fields.One2many('product.template', 'brand_id', string="Product Template")
    website_published = fields.Boolean('Available on the Website', copy=False)

    @api.multi
    def toggle_website_publish_button(self):
        self.ensure_one()
        self.website_published = not self.website_published
        return True
