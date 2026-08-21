def migrate(cr, version):
    # Fix NULL name in chorus_partner_service before NOT NULL constraint is applied
    cr.execute("""
        UPDATE chorus_partner_service
        SET name = code
        WHERE name IS NULL
    """)
