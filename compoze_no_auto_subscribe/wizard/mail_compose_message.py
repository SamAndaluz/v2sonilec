# -*- coding: utf-8 -*-

from odoo import api, fields, models


class mail_compose_message(models.TransientModel):
    """
    Overwrite to pass param to add recipients. Otherwise do not do so
    """
    _inherit = 'mail.compose.message'

    subscribe_recipients = fields.Boolean(
        string='Subscribe recipients',
        help="If checked, all recipients stated above will be added to document's followers",
    )

    @api.multi
    def send_mail(self, auto_commit=False):
        """
        Overload to clean mail_post_autofollow from context
        If at least a single wizard has not 'subscribe_recipients' checked --> we change context
        """
        no_subscribe_wiz_ids = self.filtered(lambda wiz: not wiz.subscribe_recipients)
        subscribe_flag = len(no_subscribe_wiz_ids) == 0 and True or False
        self = self.with_context(
            mail_post_autofollow=subscribe_flag,
            force_no_auto_subscription=subscribe_flag,
            mail_create_nosubscribe=not subscribe_flag,
        )
        return super(mail_compose_message, self).send_mail(auto_commit=auto_commit)
