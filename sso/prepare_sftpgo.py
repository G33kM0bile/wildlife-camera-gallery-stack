#!/usr/bin/python3
"""Stage portal separation using the existing config; never print secrets."""
import copy
import json
import os
from pathlib import Path


def stage_config(config):
    result = copy.deepcopy(config)
    bindings = result['httpd']['bindings']
    if len(bindings) != 1 or bindings[0]['port'] != 8080:
        raise ValueError('expected the verified single HTTP binding on port 8080')
    if result['data_provider'].get('pre_login_hook'):
        raise ValueError('an existing hook must be integrated explicitly')
    original = bindings[0]
    if not original['oidc'].get('implicit_roles'):
        raise ValueError('expected the verified implicit-role configuration')
    if result['httpd'].get('web_root', '') not in ('', '/'):
        raise ValueError('non-default global web_root requires separate routing')
    file_binding = copy.deepcopy(original)
    file_binding.update(port=8081, address='127.0.0.1', enable_web_admin=False, enable_web_client=True)
    admin_binding = copy.deepcopy(original)
    admin_binding.update(port=8082, address='127.0.0.1', enable_web_admin=True, enable_web_client=False)
    for binding in (file_binding, admin_binding):
        oidc = binding['oidc']
        oidc['scopes'] = list(dict.fromkeys(oidc.get('scopes', []) + ['groups']))
        oidc['custom_fields'] = list(dict.fromkeys(oidc.get('custom_fields', []) + ['groups']))
        # Only the local proxy may supply client-IP / secure-cookie headers.
        # proxy_mode=1 enables the unrelated HAProxy PROXY protocol listener.
        binding.update(proxy_mode=0, proxy_allowed=['127.0.0.1/32'],
                       client_ip_proxy_header='X-Forwarded-For', client_ip_header_depth=0)
    file_binding['oidc'].update(implicit_roles=True, role_field='')
    admin_binding['oidc'].update(implicit_roles=False, role_field='groups')
    base = admin_binding['oidc']['redirect_base_url'].rstrip('/')
    if '/oidc-admin' in base:
        raise ValueError('admin redirect prefix is already present')
    admin_binding['oidc']['redirect_base_url'] = base + '/oidc-admin'
    result['httpd']['bindings'] = [file_binding, admin_binding]
    result['data_provider']['pre_login_hook'] = '/usr/local/libexec/viltkamera-sftpgo-pre-login'
    return result


def admin_import():
    name = 'viltkamera-admin-create'
    return {
        'version': 17,
        'event_actions': [{
            'name': name, 'type': 13,
            'options': {'idp_config': {'mode': 1, 'template_admin': json.dumps({
                'username': '{{.Name}}', 'status': 1, 'permissions': ['*']
            })}}
        }],
        'event_rules': [{
            'name': name, 'status': 1, 'trigger': 7,
            'conditions': {'idp_login_event': 2},
            'actions': [{'name': name, 'order': 1, 'relation_options': {'execute_sync': True}}]
        }]
    }


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    config = json.loads(Path('/etc/sftpgo/sftpgo.json').read_text())
    write_private('/etc/viltkamera-sso/sftpgo.staged.json', stage_config(config))
    write_private('/etc/viltkamera-sso/admin-idp-import.json', admin_import())
    print('Staged config and create-only administrator import; active config unchanged.')
