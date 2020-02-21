# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers import main as WebsiteSale


class WebsiteProductBrand(WebsiteSale.WebsiteSale):

    @http.route([], type='http', auth="public", website=True)
    def shop(self, page=0, category=None, search='', ppg=False, **post):
        response = super(WebsiteProductBrand, self).shop(page=page, category=category, search=search, ppg=ppg, **post)

        brand_list = request.httprequest.args.getlist('brand')
        brand_values = [[int(x) for x in v.split("-")] for v in brand_list if v]
        brand_ids = [v[0] for v in brand_values]
        
        attrib_list = request.httprequest.args.getlist('attrib')
        attrib_values = [[int(x) for x in v.split("-")] for v in attrib_list if v]
        attrib_set = {v[1] for v in attrib_values}
        attributes_ids = {v[0] for v in attrib_values}

        Product = request.env['product.template']

        url = "/shop"
        if brand_list:
            post['brand'] = brand_list
        domain = self._get_search_domain(search, category, attrib_values)
        if 'pager' in response.qcontext:
            url = response.qcontext['pager']['page']['url']
        if 'brand' in post:
            domain += [('brand_id', 'in', brand_ids)]

        product_count = Product.search_count(domain)
        pager = request.website.pager(url=url, total=product_count, page=page, step=ppg or WebsiteSale.PPG, scope=7, url_args=post)
        products = Product.search(domain, limit=ppg, offset=pager['offset'], order=self._get_search_order(post))
        brands = request.env['product.brand'].search([('website_published', '=', True)])

        response.qcontext['pager'] = pager
        response.qcontext['products'] = products
        response.qcontext['bins'] = WebsiteSale.TableCompute().process(products, ppg or WebsiteSale.PPG)
        response.qcontext['brands'] = brands
        response.qcontext['brand_ids'] = brand_ids

        return response
