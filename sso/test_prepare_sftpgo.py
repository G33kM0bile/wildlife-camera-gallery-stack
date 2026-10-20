import unittest
from prepare_sftpgo import stage_config, admin_import


class RoutingTests(unittest.TestCase):
    def config(self):
        return {'data_provider': {'pre_login_hook': ''}, 'sftpd': {'bindings': [{'port': 2022}]},
                'ftpd': {'bindings': [{'port': 2121}]}, 'httpd': {'bindings': [{
                    'port': 8080, 'enable_web_admin': True, 'enable_web_client': True,
                    'oidc': {'implicit_roles': True, 'client_secret': 'preserve-secret',
                             'redirect_base_url': 'https://sftpgo.example.test', 'scopes': ['openid']}}]}}

    def test_portals_separate_and_transfers_unchanged(self):
        original = self.config()
        result = stage_config(original)
        files, admin = result['httpd']['bindings']
        self.assertFalse(files['enable_web_admin'])
        self.assertFalse(admin['enable_web_client'])
        self.assertTrue(files['oidc']['implicit_roles'])
        self.assertFalse(admin['oidc']['implicit_roles'])
        self.assertEqual(admin['oidc']['role_field'], 'groups')
        self.assertEqual(admin['oidc']['redirect_base_url'], 'https://sftpgo.example.test/oidc-admin')
        for binding in (files, admin):
            self.assertEqual(binding['address'], '127.0.0.1')
            self.assertEqual(binding['oidc']['client_secret'], 'preserve-secret')
            self.assertIn('groups', binding['oidc']['custom_fields'])
        self.assertEqual(result['ftpd'], original['ftpd'])
        self.assertEqual(result['sftpd'], original['sftpd'])
        self.assertEqual(original['httpd']['bindings'][0]['port'], 8080)

    def test_existing_hooks_and_unexpected_bindings_are_rejected(self):
        config = self.config()
        config['data_provider']['pre_login_hook'] = '/existing-hook'
        with self.assertRaises(ValueError):
            stage_config(config)
        config = self.config()
        config['httpd']['bindings'][0]['port'] = 9999
        with self.assertRaises(ValueError):
            stage_config(config)

    def test_auto_admin_rule_only_matches_administrator_logins(self):
        data = admin_import()
        self.assertEqual(data['event_rules'][0]['conditions']['idp_login_event'], 2)
        self.assertEqual(data['event_actions'][0]['options']['idp_config']['mode'], 1)
        self.assertNotIn('users', data)
        self.assertNotIn('admins', data)


if __name__ == '__main__':
    unittest.main()
