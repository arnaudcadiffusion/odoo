# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
################################################################################

{
    'name': 'Margin on Product, Sales, Invoices With Margin Analysis',
    'version': '19.0.0.0',
    'sequence': 4,
    'summary': 'Margin calculation on sales and invoice margin analysis report sales margin product margin invoice margin invoice report margin by percentage margin in invoice margin fix amount margin in SO margin in bill margin in vendor bill margin supplier invoice',
    'description': """
	BrowseInfo developed a new odoo/OpenERP module apps.
	This module use for calculate margin on product, margion on sales, margin on invoice. Shows total margin on orders.
	also shows margin on sale order line. Calculate margin on percentage and fixed.Margin Analysis, Margin on Product, Sale and Invoice
	margin by percentage , margin in invoice , margin fix amount, margin in SO, margin in bill , margin on sales order line , margin in sales order line
	calculate margin by pecentage , add margin on invoice and product , add margin on cost price , margin cost price , margin in cost 
	margin on Sales Analysis Report , margin on Invoices Analysis Report. INVOICE COST MARGIN REPORT 
	Print Invoice cost margin Excel report , margin in view quotation, sale and invoice
	product cost margin , sales cost margin , sales order cost margin , calculate Margin cost Analysis  
	Margin cost Analysis report 
	
   sale margin analysis report invoice
   sales margin report invoice
    invoice margin analysis report sales
   invoice margin report sales
   This odoo apps is used to apply and calculate margin on product, sale order and invoices.After installing this odoo module/app margin is automatically calculates on products, sales and invoice with margin total amount and margin percentage both. You can also see margin in Sales Analysis Report and Invoices Analysis Report pdf reports financial accounting reports in Odoo.
Este módulo se usa para calcular el margen en el producto, margion en las ventas, margen en la factura. Muestra el margen total en los pedidos.
también muestra el margen en la línea de orden de venta. Calcula el margen en porcentaje y fijo. Análisis de Margen, Margen en Producto, Venta y Factura.Ce module est utilisé pour calculer la marge sur le produit, la marge sur les ventes, la marge sur la facture. Affiche la marge totale sur les commandes.
montre également la marge sur la ligne de commande de vente. Calculer la marge sur le pourcentage et fixe. Analyse de marge, marge sur le produit, vente et facture
Dieses Modul wird für die Berechnung der Marge auf Produkt, Marge auf Umsatz, Marge auf Rechnung verwendet. Zeigt die Gesamtmarge für Bestellungen an.
zeigt auch die Marge aus der Verkaufsauftragszeile an. Berechne Marge auf Prozentsatz und reparierte. Margin Analyse, Margin auf Produkt, Verkauf und RechnungGebruik deze module voor het berekenen van de marge op het product, de marge op de verkoop, de marge op de factuur. Toont de totale marge op bestellingen.
toont ook marge op verkooporderregel. Bereken marge op percentage en fixed.Margin Analysis, Margin on Product, Sale and Invoice

Este módulo usa para calcular a margem no produto, a margem nas vendas, a margem na fatura. Mostra a margem total em pedidos.
também mostra margem na linha de ordem de venda. Calcular a margem em porcentagem e fixo.Análise de margem, margem sobre produto, venda e fatura
تستخدم هذه الوحدة لحساب الهامش على المنتج ، والهامش على المبيعات ، والهامش على الفاتورة. يعرض إجمالي الهامش على الطلبات.
كما يظهر هامش على طلب بيع الخط. حساب الهامش على النسبة المئوية والثابتة. تحليل المارجن ، الهامش على المنتج ، البيع والفاتورة
tustakhdam hadhih alwahdat lihisab alhamish ealaa almuntaj , walhamish ealaa almubieat , walhamish ealaa alfaturat. yuearid 'iijmalia alhamish ealaa altalabat.
kama yuzhir hamish ealaa talab baye alkhuta. hisab alhamish ealaa alnisbat almiawiat walththabita. tahlil almarijin , alhamish ealaa almuntaj , albaye walfatur

Este módulo se usa para calcular el margen en el producto, margion en las ventas, margen en la factura. Muestra el margen total en los pedidos.
también muestra el margen en la línea de orden de venta. Calcula el margen en porcentaje y fijo. Análisis de Margen, Margen en Producto, Venta y Factura.


    """,
    "price": 25,
    "category": "Sales",
    "currency": "EUR",
    'author': 'BROWSEINFO',
    'website': 'https://www.browseinfo.com/demo-request?app=margin&version=19&edition=Community',
    'depends': ['base','sale_management','product','sale_margin'],
    'data': [
             "views/account_invoice_view.xml",
             "views/product_view.xml",
             "views/sale_view.xml",
             ],
	'qweb': [
		],
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
    "images":['static/description/Banner.gif'],
    'live_test_url':'https://www.browseinfo.com/demo-request?app=margin&version=19&edition=Community',
    'license': 'OPL-1',
}
