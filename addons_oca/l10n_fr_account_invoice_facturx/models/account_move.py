# Copyright 2017-2022 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _cii_get_party_identification(self, commercial_partner):
        res = super()._cii_get_party_identification(commercial_partner)
        siret = commercial_partner._get_siret()
        if siret:
            res["0002"] = siret
        return res
