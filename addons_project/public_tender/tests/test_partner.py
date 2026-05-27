from odoo.tests import common
from datetime import date


class TestPartner(common.TransactionCase):
    def setUp(self):
        super(TestPartner, self).setUp()
        print('aaaaa')
        self.partner = self.env['res.partner']
        self.tender = self.env['tender.order']


    def test_partner_tenders(self):
        partner_1 = self.env['res.partner'].create({'name': 'test_partner'})
        print(partner_1)

        record = self.env['tender.order'].create({
            'name': 'testone',
            'end_of_the_tender': date(2019, 5, 10),
            'partner_ids': [(6,0,[partner_1.id])],
        })
        record2 = self.env['tender.order'].create({
            'name': 'testtwo',
            'end_of_the_tender': date(2019, 3, 10),
            'partner_ids': [(6,0,[partner_1.id])],
        })
        record3 = self.env['tender.order'].create({
            'name': 'testthree',
            'end_of_the_tender': date(2019, 9, 10),
            'partner_ids': [(6,0,[partner_1.id])],
        })
        record4 = self.env['tender.order'].create({
            'name': 'testfour',
            'partner_ids': [(6,0,[partner_1.id])],
        })

        # self.assertEqual(self.env['tender.order'].browse([record3.id]), partner_1.tender_ids,"The partner's tenders filter by end_of_the_tender")
        self.assertEqual(self.env['tender.order'].browse([record.id,record2.id,record3.id,record4.id]), partner_1.tender_ids,"The partner's tenders filter by end_of_the_tender")
