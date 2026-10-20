#!/usr/bin/python3
"""Provision browser file users from SFTPGo-validated OIDC group claims.

Never handles administrator provisioning. Non-OIDC camera logins are unchanged.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import sys

TEMPLATE = Path('/etc/viltkamera-sso/file-user-template.json')
MARKER = 'viltkamera-oidc-managed'
PHOTO_PERMISSIONS = ['list', 'download', 'upload', 'overwrite', 'delete_files', 'rename_files']


def provision(user: dict, protocol: str, template: dict | None = None) -> dict | None:
    if protocol != 'OIDC':
        return None  # Empty stdout means no changes to password/SFTP/FTP logins.
    fields = user.get('oidc_custom_fields')
    groups = fields.get('groups') if isinstance(fields, dict) else None
    if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
        raise PermissionError('missing or malformed groups')
    if not {'hunters', 'admin'}.intersection(groups):
        raise PermissionError('wildlife group membership required')
    username = user.get('username')
    if not isinstance(username, str) or not username or re.match(r'^hc960-', username, re.I):
        raise PermissionError('invalid or reserved camera identity')
    existing = bool(user.get('id'))
    if existing and user.get('description') != MARKER:
        raise PermissionError('existing file account requires explicit enrollment')
    if existing and user.get('status') != 1:
        raise PermissionError('file account is disabled')
    if template is None:
        template = json.loads(TEMPLATE.read_text(encoding='utf-8'))
    if (not isinstance(template.get('home_dir'), str)
            or not template['home_dir'].startswith('/')
            or any(type(template.get(key)) is not int or template[key] <= 0 for key in ('uid', 'gid'))):
        raise ValueError('configure the verified photo root and non-root UID/GID first')
    result = copy.deepcopy(user if existing else template)
    if existing and result.get('home_dir') != template['home_dir']:
        raise PermissionError('managed photo root differs from template')
    result.pop('oidc_custom_fields', None)
    result.update(username=username, description=MARKER)
    if not existing:
        result.update(status=1, id=0, password='', public_keys=[])
    if 'admin' in groups:
        result['permissions'] = {'/': ['*']}
    else:
        result['permissions'] = {'/': ['list']}
        for number in range(1, 6):
            result['permissions'][f'/hc960-{number:02d}'] = list(PHOTO_PERMISSIONS)
    # Do not inherit arbitrary SFTPGo groups, virtual mounts or elevated flags.
    result['groups'] = []
    result['virtual_folders'] = []
    result['filesystem'] = {'provider': 0}
    result['filters'] = {} if 'admin' in groups else {
        'denied_protocols': ['SSH', 'FTP', 'DAV'],
        'denied_login_methods': ['password'],
        'allow_api_key_auth': False,
        'web_client': ['password-change-disabled', 'password-reset-disabled',
                       'api-key-auth-change-disabled', 'publickey-change-disabled',
                       'tls-cert-change-disabled', 'shares-disabled'],
    }
    # Preserve enrolled users' MFA state while replacing authorization filters.
    if existing:
        previous_filters = user.get('filters', {})
        for key in ('totp_config', 'recovery_codes', 'two_factor_protocols', 'additional_emails'):
            if key in previous_filters:
                result['filters'][key] = copy.deepcopy(previous_filters[key])
    return result


def main() -> int:
    try:
        protocol = os.environ.get('SFTPGO_LOGIND_PROTOCOL', '')
        if protocol != 'OIDC':
            return 0
        result = provision(json.loads(os.environ['SFTPGO_LOGIND_USER']), protocol)
        if result is not None:
            print(json.dumps(result))
        return 0
    except (KeyError, ValueError, TypeError, OSError) as error:
        # No tokens, claims or account payloads in logs.
        print(f'Viltkamera OIDC login denied: {type(error).__name__}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
