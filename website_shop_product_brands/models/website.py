# -*- coding: utf-8 -*-
from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def website_publish_brand(self):
        return self.env['product.brand'].search([('website_published', '=', True)])
