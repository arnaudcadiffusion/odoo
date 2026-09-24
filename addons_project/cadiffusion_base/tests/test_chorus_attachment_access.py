from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestChorusAttachmentAccess(TransactionCase):
    """Reading ``chorus_attachment_ids`` must not scan the whole attachment
    table: the field bypasses the ir.attachment search access and relies on the
    access filter applied after the relation join."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.accountant = new_test_user(
            cls.env,
            login="chorus_accountant",
            groups="account.group_account_invoice",
            company_id=company.id,
        )
        cls.invoice = cls.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": company.partner_id.id,
        })
        cls.attachment = cls.env["ir.attachment"].create({
            "name": "chorus.pdf",
            "raw": b"%PDF-1.4",
            "res_model": "account.move",
            "res_id": cls.invoice.id,
        })
        cls.invoice.chorus_attachment_ids = cls.attachment

    def test_field_bypasses_attachment_search_access(self):
        field = self.env["account.move"]._fields["chorus_attachment_ids"]
        self.assertTrue(field.bypass_search_access)

    def test_accountant_reads_invoice_chorus_attachments(self):
        invoice = self.invoice.with_user(self.accountant)
        invoice.invalidate_recordset()
        self.assertEqual(invoice.chorus_attachment_ids, self.attachment)
