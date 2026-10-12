# Rauthy SSO with local-login fallback

This deployment can use Rauthy for browser SSO without removing any existing
password login. Grafana is configured separately and is not changed by this
guide.

The three clients are confidential authorization-code clients. Register only
the exact callback shown here. Enable PKCE S256 for PiGallery2 and the camera
setup site, but leave both PKCE options disabled for SFTPGo: its current OIDC
login does not send a `code_challenge`, and Rauthy otherwise rejects the
authorization request with HTTP 400.

| Client ID | Service | Redirect URI |
| --- | --- | --- |
| `pigallery2` | PiGallery2 | `https://viltkamera.example.com/pgapi/auth/oidc/callback` |
| `sftpgo` | SFTPGo | `https://sftpgo.example.com/web/oidc/redirect` |
| `kamera` | Camera setup | `https://kamera.example.com/auth/oidc/callback` |

Use the Rauthy issuer URL, not the authorization endpoint, in application
configuration. For example: `https://auth.example.com/auth/v1`. SFTPGo
requires the configured URL to match the discovery document byte-for-byte;
Rauthy publishes the issuer with a trailing slash, so use
`https://auth.example.com/auth/v1/` in SFTPGo.

## Stable mapping to existing local accounts

Rauthy normalizes `preferred_username` to lowercase, while an existing local
PiGallery2 or SFTPGo account can contain uppercase letters. Do not rename or
delete the local account. Instead:

1. Create a Rauthy string user attribute named `local_username`.
2. Set it to the exact existing local account name for each authorized user.
3. Create a custom scope named `local_username`.
4. Map the attribute into both the ID token and access token, and enable
   "Emit claims at token root" so the claim is named `local_username`.
5. Allow that scope for the PiGallery2 and SFTPGo clients.

This preserves all roles, permissions and password credentials already stored
in the applications.

## PiGallery2

Keep `Users.authenticationRequired` enabled and set:

```json
{
  "enabled": true,
  "issuerUrl": "https://auth.example.com/auth/v1",
  "clientId": "pigallery2",
  "clientSecret": "<stored only in the protected production config>",
  "redirectUri": "https://viltkamera.example.com/pgapi/auth/oidc/callback",
  "scopes": ["openid", "profile", "email", "local_username"],
  "usernameClaim": "local_username",
  "autoCreateUser": false
}
```

`autoCreateUser=false` is intentional. Rauthy users can only enter when the
mapped local PiGallery2 user already exists. The original PiGallery2 password
form remains available.

For PiGallery2 3.5.x, set both the Rauthy client's **Access Token Algorithm**
and **ID Token Algorithm** to `RS256`. Its bundled OIDC client does not accept
Rauthy's EdDSA default and otherwise also rejects the `at_hash` value when the
two token algorithms differ.

## SFTPGo

Configure the HTTP binding OIDC block with:

- config URL: `https://auth.example.com/auth/v1/` (trailing slash required)
- redirect base URL: `https://sftpgo.example.com`
- username field: `local_username`
- scopes: `openid,profile,email,local_username`
- implicit roles: enabled
- PKCE `plain` and `S256`: disabled in the Rauthy client
- client secret file: a root-owned file outside the Git checkout

Do not change `enabled_login_methods` or `disabled_login_methods`. OIDC then
adds a browser login option while passwords, SSH keys and camera uploads keep
working independently. Existing SFTPGo admin and user rows remain the source
of authorization.

## Camera setup site

Copy `camera-admin/oidc.env.example` to
`/etc/viltkamera-camera-admin/oidc.env`, set the real URLs and list only the
Rauthy `preferred_username` values allowed to administer cameras. Store the
client secret in `/etc/viltkamera-camera-admin/oidc-client-secret`, readable
only by root and the service group.

The camera setup app uses authorization code with PKCE, exchanges the code on
the server, verifies identity through Rauthy's UserInfo endpoint and creates
only its own short-lived local session. Its original SFTPGo-admin login remains
visible below the Rauthy button.

## Rollback

1. Disable OIDC in PiGallery2 and restart its container.
2. Restore SFTPGo's previous `sftpgo.json` and restart `sftpgo`.
3. Remove or rename `/etc/viltkamera-camera-admin/oidc.env` and restart
   `viltkamera-camera-admin`.

Because local users and credentials are never removed, rollback does not
require password resets.

## Login-button branding

The reference deployment labels the SSO action `Login med MinSin SSO` in all
three services. Camera setup keeps the label in `static/index.html`, and the
PiGallery2 build overlay replaces its upstream `Login with <provider>` label.
SFTPGo reads `login.signin_openid` from its English translation file; package
upgrades can replace that file, so verify the label after every SFTPGo update.
