# Group access: hunters and global administrators

## Requested policy

Exact Rauthy group names, verified in production on 2026-10-20:

| Group | Intended access |
| --- | --- |
| `hunters` | View gallery, mark/unmark sightings, edit camera settings, manage/delete camera photos through SFTPGo WebClient |
| `admin` | Full administration across all sites, including Rauthy; supersedes hunters |
| Neither | No new Viltkamera SSO access |

Group membership must be administrator-controlled. Never make group or role
attributes user-editable, or place self-registered users into `admin`.
No Rauthy user accounts are created by the application provisioning code:
create/register the identity in Rauthy, assign its group and a unique
`preferred_username`, then provision application accounts at first login.
For SFTPGo, set the administrator-controlled `local_username` attribute on the
Rauthy identity; preserve exact capitalization of existing local names.

## Current implementation and verification status

Production Rauthy was observed running 0.37.1. Its existing `admin`, `hunters`,
`gamers`, `lab`, and `user` groups were inspected. The `groups` scope was added
to the default scopes for clients `kamera`, `pigallery2`, and `sftpgo`, preserving
`openid` and the existing allowed scopes. No membership, signing algorithm,
redirect URI, login prefix, or password changes were made.

The following application changes are prepared locally, not yet deployed or
tested against production. The host identified by the operator is
`192.168.1.246`; its containers and application versions still require live
verification. SSH was reachable but existing authentication was rejected.

## Camera setup

Deploy the updated `camera-admin/app.py` through the existing installer and
retain the existing secret file, issuer, redirect URI and local-login fallback.
Merge these entries into `/etc/viltkamera-camera-admin/oidc.env`:

```ini
CAMERA_ADMIN_OIDC_SCOPES=openid profile email groups
CAMERA_ADMIN_OIDC_ALLOWED_GROUPS=hunters,admin
```

Preserve the existing `CAMERA_ADMIN_OIDC_ALLOWED_USERS` during migration.
It remains an explicit access exception; review/remove it after group access
has been tested. The default example leaves it empty. A verified UserInfo
group claim permits a session without creating an SFTPGo administrator or a
camera-app local account. Group matching is exact and case-sensitive.

## PiGallery2

Build the existing pinned 3.5.2 image with `pigallery2-map/build.sh`; it now
also includes the OIDC group policy overlay. Do not enable group auth with an
upstream image that lacks this overlay. Enable `PIGALLERY_OIDC_GROUP_AUTH=1`
in the actual Compose service and recreate it. Add `groups` to
`Users.oidc.scopes`, preserve the existing scopes and username claim, and set
`Users.oidc.autoCreateUser=true`.

With group auth enabled, the validated ID token must contain an array of group
names. `hunters` maps to PiGallery's `User` role, sufficient for both sighting
buttons. `admin` maps to `Admin` and bypasses gallery query projections.
Role membership is reapplied on each SSO login, including demotion from Admin.
Existing password hashes are retained; new accounts get cryptographically
random passwords that are not returned to the user. `local_username` is used
when present, otherwise `preferred_username`; email-only identities are
rejected in group mode. Disabling the group-auth environment flag restores
upstream mapping, so restore `autoCreateUser=false` as part of rollback.

Keep the photo bind mount read-only. Photo deletion is provided by SFTPGo;
sighting marks are stored separately in the gallery extension's writable state.

## SFTPGo 2.7.5: user provisioning

Back up the provider database and active config first. Check for existing
pre-login hooks, identity-provider event rules, and group settings that disable
the pre-login hook before replacing or combining them. An existing IDP account
check rule can bypass the pre-login hook; do not enable a user-provisioning IDP
rule alongside this hook.

Install `sso/sftpgo_pre_login.py` root-owned, executable, outside the checkout,
for example `/usr/local/libexec/viltkamera-sftpgo-pre-login`.
Copy `sso/file-user-template.example.json` to
`/etc/viltkamera-sso/file-user-template.json`. Set its `uid` and `gid` to the
verified, non-root numeric IDs used to access the photo storage **inside the
SFTPGo LXC**. Verify the mounted photo root and ACLs; do not guess IDs or change
the unprivileged LXC mapping. Null IDs intentionally fail closed.

Merge into the existing config:

```json
{
  "data_provider": {
    "pre_login_hook": "/usr/local/libexec/viltkamera-sftpgo-pre-login"
  }
}
```

Preserve the existing OIDC issuer (including trailing slash), credentials,
RS256 signing and disabled PKCE settings. Add `groups` to OIDC `scopes` and
`custom_fields`; retain `username_field=local_username`.

The hook provisions browser file users only. It makes no changes for FTP,
SSH/SFTP, DAV or local HTTP password logins. OIDC claims must include `hunters`
or `admin`; `hc960-*` identities are rejected for browser provisioning. Hunters
receive list/download/upload/overwrite/delete-files/rename-files permissions
inside the five camera directories. They cannot delete or rename the camera
directories themselves or administer SFTPGo. An admin file user receives `*`
over the verified storage root. File-user access never confers WebAdmin access.

Existing file accounts require explicit review and enrollment by setting their
description to `viltkamera-oidc-managed`. Their home directory must match the
template; disabled accounts remain denied. Managed permissions are synchronized
at each OIDC login. The hook preserves existing credentials, replaces inherited
groups/mounts/filters, and limits hunters to browser access. Admin file users
receive no protocol restrictions from the hook.
Hunters cannot enable local password/API-key login or public shares through
WebClient; this keeps provisioned file access tied to OIDC group checks.

## SFTPGo administrator provisioning and portal separation

SFTPGo 2.7.5 does not treat its administrator store and file-user store as the
same account. Do not combine `implicit_roles=true` with an unrestricted
automatic administrator-creation template: any hunter clicking the WebAdmin
login would then request an administrator identity.

Its explicit mapping supports `role_field=groups`, `implicit_roles=false`,
where the exact value `admin` authorizes WebAdmin. A synchronous IDP-login-admin
account-check action can create an administrator with this template:

```json
{
  "username": "{{.Name}}",
  "status": 1,
  "permissions": ["*"]
}
```

Use create-only mode initially to preserve existing administrator records.
With explicit role mapping, an `admin` identity cannot log in to WebClient on
the same binding; SFTPGo rejects admin-role tokens there. Therefore **full
administration plus direct browser file access for the same admin identity
still needs a separately routed file-client/admin binding arrangement**.
A safe arrangement uses two HTTP bindings with separate public origins:
file-only binding (`enable_web_admin=false`, implicit user roles) and admin-only
binding (`enable_web_client=false`, explicit `groups` role mapping). Give each
binding the matching Rauthy callback, route each origin only to its intended
binding, and prevent bypass through another exposed admin-enabled binding.
Verify callback/audience handling and active proxy configuration before applying.
Do not enable automatic administrator provisioning until that separation is
implemented and tested. This routing is not included in the local code patch.

## Global admin across other sites

Rauthy groups do not automatically grant built-in Rauthy roles or local app
permissions. A global admin rollout remains pending for all services below:

| Service | Required mapping / check |
| --- | --- |
| Rauthy | Assign built-in `rauthy_admin` to every approved `admin` identity; group membership alone is insufficient. Keep the emergency administrator. |
| Cloudflare Access | Permit `admin` identities in each app policy, while retaining app authorization checks. |
| Grafana | Map `admin` to server administrator; verify server-admin mapping is enabled and user sync works. |
| Proxmox VE (Labs 1–4) | Verify each OIDC realm's group mapping and assign Administrator on `/` with propagation to the mapped admin group. |
| Proxmox Backup Server (Labs 2–4) | Verify realm/account provisioning and grant Admin on `/` through the permissions supported by the installed version. |
| Gramps Web, Tandoor, Nexterm, NetworkOptimizer | Inspect each installed implementation and explicitly map/approve application administrators; do not assume an OIDC group grants privileges. |

No other site's ACLs, roles or auto-provisioning settings have been changed.
Automatic Rauthy role inheritance from a group is not implemented by this patch;
onboarding/offboarding must update both membership and built-in roles.

## Acceptance and rollback

Local checks: Python camera-admin suite, Python SFTPGo hook suite and Node 24+
`node --test sso/pigallery-oidc.test.cjs`. The Node harness executes the actual
callback overlay with mocked validated token/client and account store; it does
not replace a full TypeScript/image build or live identity-provider test.

Before rollout completion, verify with disposable media: a new hunter can
mark/unmark sightings, save camera settings and delete a test photo; a new admin
can administer every intended service and manage files; an unrelated user
cannot create an account; removing membership denies the next login; an admin
losing `admin` is demoted; camera uploads still work; local recovery still works.
Existing app sessions must be revoked on membership changes for immediate
revocation, and app-local credentials must be reviewed separately.

Rollback: restore the saved app configs/provider state and previous image;
restore `autoCreateUser=false` before disabling the PiGallery group overlay;
restore the prior camera OIDC environment and SFTPGo hook/event rules. The
added Rauthy default scope can be removed by restoring each client's previous
default of `openid`. Do not remove local emergency accounts or photo data.
