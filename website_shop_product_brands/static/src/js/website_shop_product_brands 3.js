odoo.define('website_shop_product_brands.snippet_brand', function (require) {
'use strict';
var snippets_editor = require('web_editor.snippet.editor');

snippets_editor.Class.include({
    _updateCurrentSnippetEditorOverlay: function () {
        this._super.apply(this, arguments);
        $('.brand_carousel').carousel({
          interval: 10000
        })

        $('.brand_carousel .carousel-item').each(function(e){
            var next = $(this).next();

            if (!next.length) {
                next = $(this).siblings(':first');
            }
            next.children(':first-child').clone().appendTo($(this));
            
            for (var i=0; i<2; i++) {
                next=next.next();
                if (!next.length) {
                    next = $(this).siblings(':first');
                }
                next.children(':first-child').clone().appendTo($(this));
            }
        });
    },
});
});
