# -*- coding: utf-8 -*-
import random

from odoo import api, fields, models


class ChessOdooFact(models.Model):
    _name = 'chess.odoo.fact'
    _description = 'Odoo Fun Facts'

    fact = fields.Text(string='Fact', required=True)
    active = fields.Boolean(default=True)
    category = fields.Selection([
        ('history', 'Odoo History'),
        ('feature', 'Odoo Feature'),
        ('tip', 'Usage Tip'),
        ('fun', 'Fun Fact'),
    ], default='fun', string='Category')

    @api.model
    def get_random_fact(self):
        """Return a random active fact."""
        facts = self.search([('active', '=', True)])
        if facts:
            return random.choice(facts).fact
        return "Did you know? Odoo was founded in 2005 as TinyERP!"

    @api.model
    def get_random_facts(self, count=5):
        """Return multiple random facts."""
        facts = self.search([('active', '=', True)])
        if len(facts) <= count:
            return facts.mapped('fact')
        return random.sample(facts.mapped('fact'), count)
