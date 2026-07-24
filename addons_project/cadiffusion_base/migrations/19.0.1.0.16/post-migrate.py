"""
Migration 19.0.1.0.16 — post-upgrade

Configure les codes UNECE (Type=VAT, Catégorie=E) sur les taxes de vente
« TVA 0% EXO » qui n'en ont pas. Sans ce type, generate_facturx_xml n'émet
aucun bloc ApplicableTradeTax d'en-tête pour une facture dont toutes les
lignes portent une telle taxe (cas réel : facture 260470 d'intérêts
moratoires, journal « Factures IM ») → XML rejeté par le XSD CII avec
l'erreur trompeuse « SpecifiedTradePaymentTerms: This element is not
expected », envoi Chorus impossible.

Déjà appliqué à la main sur la base Test le 24/07/2026 (taxes 876 et 879,
via API) ; ce script aligne la production et toute base restaurée. La
logique vit dans ``cadiffusion_base._configure_unece_exo_taxes``, également
exécutée par le post_init_hook pour les installs fraîches (rebuilds Odoo.sh
par upgrade complet) où les scripts de migrations/ ne tournent pas.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import _configure_unece_exo_taxes


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _configure_unece_exo_taxes(env)
