# Source Generated with Decompyle++
# File: coins_calendar_helpers.cpython-312.pyc (Python 3.12)

'''Helpers calendrier Coins Marocain (résolution tags / alarmes).'''
from odoo import models
COLOR_HAMMAM = 1
COLOR_VILLA = 7
COLOR_FERMETTE = 3
COLOR_LOCATION = 8
COLOR_DEFAULT = 5

class CalendarEventTypeCoins(models.Model):
    _inherit = 'calendar.event.type'
    
    def _coins_categ_for_package_type(self, package_type):
        '''Retourne le tag calendar selon le palier forfait.'''
        xmlid = 'coins_marocain.calendar_categ_coins_detente'
        if package_type in ('palier_1_detente', 'palier_2_cross_sell'):
            xmlid = 'coins_marocain.calendar_categ_coins_hammam'
        elif package_type in ('palier_3_combo_complet', 'palier_4_villa_bbq', 'palier_5_villa_cuisine', 'palier_6_villa_soiree_option'):
            xmlid = 'coins_marocain.calendar_categ_coins_villa'
        elif package_type in ('palier_7_fermette_dj', 'palier_8_fermette_camping'):
            xmlid = 'coins_marocain.calendar_categ_coins_fermette'
        return self.env.ref(xmlid, raise_if_not_found = False)

    
    def _coins_color_for_package_type(self, package_type):
        if package_type in ('palier_1_detente', 'palier_2_cross_sell'):
            return COLOR_HAMMAM
        if None in ('palier_3_combo_complet', 'palier_4_villa_bbq', 'palier_5_villa_cuisine', 'palier_6_villa_soiree_option'):
            return COLOR_VILLA
        if None in ('palier_7_fermette_dj', 'palier_8_fermette_camping'):
            return COLOR_FERMETTE


