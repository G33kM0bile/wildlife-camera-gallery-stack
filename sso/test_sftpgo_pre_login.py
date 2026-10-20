import unittest
from sftpgo_pre_login import provision, MARKER


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.template = {'home_dir': '/srv/sftpgo/data', 'uid': 1001, 'gid': 1001}
        self.user = {'id': 0, 'username': 'hunter-one', 'oidc_custom_fields': {'groups': ['hunters']}}

    def test_new_hunter_can_manage_photos_but_not_camera_directories(self):
        result = provision(self.user, 'OIDC', self.template)
        self.assertEqual(result['permissions']['/'], ['list'])
        for number in range(1, 6):
            permissions = result['permissions'][f'/hc960-{number:02d}']
            self.assertIn('delete_files', permissions)
            self.assertIn('upload', permissions)
            self.assertNotIn('delete_dirs', permissions)
            self.assertNotIn('*', permissions)
        self.assertNotIn('oidc_custom_fields', result)
        self.assertIn('password', result['filters']['denied_login_methods'])
        self.assertFalse(result['filters']['allow_api_key_auth'])
        self.assertIn('api-key-auth-change-disabled', result['filters']['web_client'])
        self.assertIn('shares-disabled', result['filters']['web_client'])
        self.assertEqual(self.user['id'], 0)

    def test_admin_precedence(self):
        self.user['oidc_custom_fields']['groups'] = ['hunters', 'admin']
        result = provision(self.user, 'OIDC', self.template)
        self.assertEqual(result['permissions'], {'/': ['*']})
        self.assertEqual(result['filters'], {})

    def test_missing_malformed_and_unrelated_groups_denied(self):
        for groups in (None, 'hunters', ['hunters-other'], ['Hunters'], ['hunters', 1], []):
            with self.subTest(groups=groups), self.assertRaises(PermissionError):
                self.user['oidc_custom_fields']['groups'] = groups
                provision(self.user, 'OIDC', self.template)

    def test_camera_password_uploads_are_untouched(self):
        for protocol in ('FTP', 'SSH', 'HTTP', 'DAV', ''):
            self.assertIsNone(provision({'username': 'hc960-01'}, protocol))
        self.user['username'] = 'HC960-01'
        with self.assertRaises(PermissionError):
            provision(self.user, 'OIDC', self.template)

    def test_existing_account_requires_enrollment(self):
        self.user.update(id=12, home_dir='/srv/sftpgo/data', status=1)
        with self.assertRaises(PermissionError):
            provision(self.user, 'OIDC', self.template)
        self.user.update(description=MARKER, password='existing-hash')
        result = provision(self.user, 'OIDC', self.template)
        self.assertEqual(result['password'], 'existing-hash')
        self.user['status'] = 0
        with self.assertRaises(PermissionError):
            provision(self.user, 'OIDC', self.template)

    def test_invalid_template_and_changed_root_are_denied(self):
        for uid in (None, 0, -1, '1001', True):
            template = dict(self.template, uid=uid)
            with self.assertRaises(ValueError):
                provision(self.user, 'OIDC', template)
        self.user.update(id=12, home_dir='/other', status=1, description=MARKER)
        with self.assertRaises(PermissionError):
            provision(self.user, 'OIDC', self.template)

    def test_membership_removal_denied_and_admin_demotion_applied(self):
        self.user.update(id=12, home_dir='/srv/sftpgo/data', status=1, description=MARKER,
                         permissions={'/': ['*']})
        result = provision(self.user, 'OIDC', self.template)
        self.assertEqual(result['permissions']['/'], ['list'])
        self.user['oidc_custom_fields']['groups'] = []
        with self.assertRaises(PermissionError):
            provision(self.user, 'OIDC', self.template)


if __name__ == '__main__':
    unittest.main()
