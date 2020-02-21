# -*- coding: utf-8 -*-
from odoo import api, exceptions, fields, models, _


class ProductTemplate(models.Model):
    _inherit = "product.template"


    # @api.multi
    # def _get_custom_name(self):
    #     for rec in self:
    #         rec.custom_name = rec.product_variant_id.custom_name


    # @api.multi
    # def _inverse_custom_name(self):
    #     for rec in self:
    #         rec.product_variant_id.custom_name = rec.custom_name
         

    # custom_name =  fields.Char(string='Nombres anteriores',
    #                             required=True,
    #                             compute='_get_custom_name',
    #                           inverse='_inverse_custom_name')
    custom_name =  fields.Char(string='Nombres anteriores',
        required=True)


class ProductProduct(models.Model):
    _inherit = 'product.product'


    # custom_name =  fields.Char(string='Nombres anteriores',
    #                             required=True)
    custom_name =  fields.Char(string='Nombres anteriores',
        related='product_tmpl_id.custom_name',
        store=True)