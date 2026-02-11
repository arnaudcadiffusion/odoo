from odoo import api, fields, models, _
from odoo.exceptions import UserError
import requests
import json
import logging

logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    label_printed = fields.Boolean(default=False, copy=False, tracking=True)
    client_order_ref = fields.Char(compute="_compute_client_order_ref")

    @api.depends("sale_id", "backorder_id")
    def _compute_client_order_ref(self):
        for picking in self:
            picking.client_order_ref = (
                picking.sale_id.client_order_ref
                or picking.backorder_id.sale_id.client_order_ref
                or ""
            )

    def send_label_print(self):
        server_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cadiffusion_picking_label_print.picking_label_print_server_url")
        )
        message = None
        if self.label_printed:
            raise UserError(
                _(
                    'The label has already been printed,\n you may check off the "Label Printed" to re-print!'
                )
            )
        if not server_url:
            raise UserError(
                _(
                    "Please configure webhook URL in the settings for printing your label."
                )
            )
        server_url = f"{server_url}?id={self.id}"
        try:
            response = requests.post(server_url, timeout=5)
            response.raise_for_status()
            response_json = json.loads(response.content)
        except requests.exceptions.RequestException as e:
            logger.error(f'Error while printing label for picking {self.name}: {str(e)}')
            raise UserError(_("Error while printing the label: " + str(e)))
        message = response_json.get("message")
        if message and "impression en cours" in message.lower():
            self.label_printed = True
        ctx = {
            "default_message": message,
        }
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.label.print.message",
            "views": [(False, "form")],
            "view_id": False,
            "target": "new",
            "context": ctx,
        }

    def send_transport(self):
        server_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cadiffusion_picking_label_print.picking_transpot_server_url")
        )
        message = None
        if not server_url:
            raise UserError(
                _(
                    "Please configure webhook URL in the settings for transporting your picking."
                )
            )
        server_url = f"{server_url}?id={self.id}"
        try:
            response = requests.post(server_url)
            logger.info(
                "Trigger transport for picking %s ,response: %s %s"
                % (self.name, response.status_code, response.content)
            )
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error while transport: " + str(e)))
        message = _("✅ Searching for the best carrier…")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Transport",
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
