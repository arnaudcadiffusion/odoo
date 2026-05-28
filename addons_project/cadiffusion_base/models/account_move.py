# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    x_studio_code_taxe = fields.Char(
        string='Code taxe',
        related='tax_ids.name',
        store=True,
        translate=False,
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_studio_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='partner_id.parent_id.x_studio_code_service_chorus',
        store=True,
    )
    x_studio_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='partner_id.category_id',
    )
    x_studio_field_rHWR6 = fields.Many2many(
        'res.partner',
        'account_move_partner_rel',
        'move_id',
        'partner_id',
        string='Contact',
    )

    is_draft_duplicated_ref_ids = fields.Boolean(
        string='Has Draft Duplicates',
        compute='_compute_is_draft_duplicated_ref_ids',
    )

    @api.depends('duplicated_ref_ids')
    def _compute_is_draft_duplicated_ref_ids(self):
        for move in self:
            drafts = move.duplicated_ref_ids.filtered(lambda m: m.state == 'draft')
            move.is_draft_duplicated_ref_ids = bool(drafts)
            move.is_exact_move_duplicate = any(
                d.amount_total == move.amount_total for d in drafts
            )

    def action_delete_duplicates(self):
        drafts = self.duplicated_ref_ids.filtered(lambda m: m.state == 'draft')
        drafts.button_cancel()
        drafts.unlink()
        return True


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    x_studio_cmup = fields.Float(
        string='CMUP',
        related='sale_line_ids.purchase_price',
        store=True,
        readonly=True,
    )
    x_studio_date = fields.Date(
        string='Date Facture',
        related='move_id.date',
        store=True,
        readonly=True,
    )


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    x_studio_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='move_id.x_studio_code_service_chorus',
    )
    x_studio_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='move_id.x_studio_etiquettes_clients',
    )
    x_studio_field_rHWR6 = fields.Many2many(
        'res.partner',
        string='Contact',
        related='move_id.x_studio_field_rHWR6',
    )


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    x_studio_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='move_id.x_studio_code_service_chorus',
    )
    x_studio_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='move_id.x_studio_etiquettes_clients',
    )
    x_studio_field_rHWR6 = fields.Many2many(
        'res.partner',
        string='Contact',
        related='move_id.x_studio_field_rHWR6',
    )
