# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import models


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _register_hook(self):
        """Cancel the automatic ``generic_coa`` chart installation.

        Odoo 19 auto-installs the ``generic_coa`` chart of accounts when the
        ``account`` module is installed on a fresh database. It is scheduled on
        the registry during install and executed in this hook (STEP 9, after
        all modules and their ``post_init_hook`` have run).

        That auto-install DELETES any chart data created before it ran
        (accounts, journals, taxes, fiscal positions) because the company has
        no journal entries yet, then loads ``generic_coa``.

        FlousFlow Accounting ships its own chart templates and loads them in
        its ``post_init_hook``, so we cancel the scheduled auto-install to let
        the FlousFlow chart survive.
        """
        registry = self.env.registry
        if hasattr(registry, '_auto_install_template'):
            del registry._auto_install_template
        return super()._register_hook()
