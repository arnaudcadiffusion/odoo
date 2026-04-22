"""
Migration 19.0.1.0.4 — post-upgrade

Redirige toutes les actions rapport account.move qui utilisent encore
des templates Odoo standard ou Studio (copies) vers notre template custom.
Couvre :
  - account.report_invoice_copy_1  (Studio "Factures Autre" migré depuis v15)
  - account.report_invoice_copy_*  (toute autre copie Studio)
  - tout pattern studio_report*    (rapports Studio génériques)
"""


def migrate(cr, _version):
    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_with_payments'
        WHERE model = 'account.move'
          AND (
              report_name LIKE 'account.report_invoice_copy%'
              OR report_name LIKE '%studio_report%'
          )
    """)
