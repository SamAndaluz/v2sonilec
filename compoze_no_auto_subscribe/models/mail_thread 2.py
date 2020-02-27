# -*- coding: utf-8 -*-

from odoo import api, models


class mail_thread(models.AbstractModel):
    """
    Overwrite to make subsription only in
    """
    _inherit = "mail.thread"

    @api.multi
    def _message_subscribe(self, partner_ids=None, channel_ids=None, subtype_ids=None, customer_ids=None):
        """
        Overwrite since to take into account the level :
          * a few modules (project, sale, purchase, account, hr_salary) force autosubscription in the message post and
            do not rely upon mail.compose.message

        We prefer private '_message_subscribe' to public 'message_subscribe' since:
          * it is used rarer and, hence, there are less chances that another third party module overdoes it
        """
        if self._context.get("mail_post_autofollow") and not self._context.get("force_no_auto_subscription"):
            return True
        return super(mail_thread, self)._message_subscribe(partner_ids=partner_ids, channel_ids=channel_ids,
                                                          subtype_ids=subtype_ids, customer_ids=customer_ids)
