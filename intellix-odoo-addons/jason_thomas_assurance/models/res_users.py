# -*- coding: utf-8 -*-
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _jt_admin_users(self):
        group = self.env.ref(
            'jason_thomas_assurance.group_jt_admin',
            raise_if_not_found=False,
        )
        if not group:
            return self.env['res.users']
        return self.filtered(lambda u: group in u.group_ids)

    def _sync_doorway_role_groups(self):
        jt_users = self._jt_admin_users()
        return super(ResUsers, self - jt_users)._sync_doorway_role_groups()

    def _sync_doorway_segment_groups(self):
        jt_users = self._jt_admin_users()
        return super(ResUsers, self - jt_users)._sync_doorway_segment_groups()

    def _sync_doorway_assigned_pipeline_access(self):
        jt_users = self._jt_admin_users()
        return super(ResUsers, self - jt_users)._sync_doorway_assigned_pipeline_access()

    def _sync_pipeline_tab_groups(self):
        jt_users = self._jt_admin_users()
        return super(ResUsers, self - jt_users)._sync_pipeline_tab_groups()
