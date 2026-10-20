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
SFTPGo uses the standard `preferred_username` claim for new SSO accounts.
Existing local accounts remain available with their original names. An owner
whose legacy local name differs in capitalization may get a separate SSO
account; this mapping change was explicitly approved by the operator.
PiGallery still prefers the existing `local_username` claim when present and
falls back to `preferred_username` for new identities.

## Current implementation and verification status

Production Rauthy was observed running 0.37.1. Its existing `admin`, `hunters`,
`gamers`, `lab`, and `user` groups were inspected. The `groups` scope was added
to the default scopes for clients `kamera`, `pigallery2`, and `sftpgo`, preserving
`openid` and the existing allowed scopes. The additional SFTPGo admin callback
`https://sftpgo.8370.no/oidc-admin/web/oidc/redirect` was registered. No
membership, signing algorithm, login prefix, or password changes were made.

Live inventory verified Foxtrot in Lab2/YTR: CT 107 is SFTPGo 2.7.6 with the
camera-settings app; CT 110 is PiGallery2 3.5.2. Deployment was carried out
through the signed-in Proxmox node shell. CT 107 now runs the group-aware
camera app, file-user hook, administrator creation rule and dedicated Caddy
portal router. CT 110 runs `viltkamera/pigallery2:3.5.2-group-access`, layered
on the existing `3.5.2-map-camera-pins-minsin-sso` image. Its photo mount
remains read-only and the container reported healthy.

Application configs and consistent SQLite backups were saved under
`/root/viltkamera-access-backup-20261020` inside each CT. Both database backups
passed `PRAGMA integrity_check`. Public login pages, separate OIDC callback
routes, internal portal separation and the existing 2022/2121 upload listeners
were verified. Gallery SSO succeeded. After the approved standard-username
change, the owner's personal Rauthy account successfully entered both SFTPGo
WebClient and WebAdmin; new `pao87` accounts were provisioned while the legacy
`PAO87` accounts remained intact. The file portal displayed the camera folders
and upload controls, and WebAdmin displayed user and administrator management.
Camera-settings SSO reached the callback but Rauthy rejected the existing
client secret (HTTP 401). The operator has been asked to synchronize that
credential; camera SSO acceptance remains pending. No hunter identities or
production test photos were created, and no camera settings were saved.

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

For a full rebuild, use `pigallery2-map/build.sh`; it includes the group-policy
overlay. For the deployed backend-only update, run the pinned compiler in
`sso/package.json` to regenerate `sso/gallery-backend`, then build
`sso/gallery.Dockerfile` with `BASE_IMAGE` set to the existing custom image.
This retains the existing frontend and map build. Do not enable group auth with an
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

## SFTPGo 2.7.6: user provisioning

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
`custom_fields`; use `username_field=preferred_username` for automatic accounts.

The hook provisions browser file users only. It makes no changes for FTP,
SSH/SFTP, DAV or local HTTP password logins. OIDC claims must include `hunters`
or `admin`; `hc960-*` identities are rejected for browser provisioning. Hunters
receive list/download/upload/overwrite/delete-files/rename-files permissions
inside the five camera directories. They cannot delete or rename the camera
directories themselves or administer SFTPGo. An admin file user receives `*`
over the verified storage root. File-user access never confers WebAdmin access.

Existing hunter file accounts require explicit review and enrollment by setting their
description to `viltkamera-oidc-managed`. Their home directory must match the
template; disabled accounts remain denied. Managed permissions are synchronized
at each OIDC login. The hook preserves existing credentials, replaces inherited
groups/mounts/filters, and limits hunters to browser access. Admin file users
receive no protocol restrictions from the hook.
An existing file account authenticated with the trusted `admin` group may keep
its already approved home directory, filesystem and virtual mounts, without
manual enrollment. Disabled accounts still fail; credentials and MFA state are
preserved. Removing `admin` requires explicit hunter enrollment if its legacy
home directory differs from the hunters template.
Hunters cannot enable local password/API-key login or public shares through
WebClient; this keeps provisioned file access tied to OIDC group checks.

## SFTPGo administrator provisioning and portal separation

SFTPGo 2.7.6 does not treat its administrator store and file-user store as the
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

The deployed arrangement keeps the existing public origin and port 8080:

| Public route | Internal target | Authorization |
| --- | --- | --- |
| `/web/client/*` and normal file callback | `127.0.0.1:8081` | File-only binding, implicit user role; group-enforcing pre-login hook |
| `/web/admin/*` | `127.0.0.1:8082` | Admin-only binding, explicit `groups` role mapping |
| `/oidc-admin/web/oidc/redirect` | `127.0.0.1:8082/web/oidc/redirect` | Distinct registered callback for the admin binding |

`sso/Caddyfile` implements that routing. The package's unused default Caddy
service is masked; `viltkamera-sftpgo-proxy.service` runs the dedicated router
as `nobody`, with a private state directory. Both backend listeners bind only
to loopback and accept forwarded headers only from loopback. `proxy_mode=0`
is intentional: `1` enables the unrelated HAProxy PROXY-protocol listener and
prevents startup without additional common proxy configuration.

`sso/prepare_sftpgo.py` stages the config while retaining credentials and
non-HTTP transfer settings. It also generates the create-only admin IDP action
and rule, imported using SFTPGo's native `initprovider --loaddata-from` command
with the service stopped. Existing user/admin rows are not included in that
import. The five pre-existing camera heartbeat rules were retained. Local
admin password login remains on the admin binding.

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

### Lab2 follow-up prepared, not deployed

Live inspection confirmed PVE 9.2.11 supports `groups-claim`,
`groups-autocreate`, and `groups-overwrite`. Realm `rauthy` currently has no
group mapping; the existing capitalized local group `Admin` has propagated
`Administrator` on `/`. The proposed mapping is `groups-claim=groups`, an
explicit `admin-rauthy` group with that same root role, and
`groups-autocreate=0`. Enable `groups-overwrite=1` only as an explicit migration:
it replaces local PVE group memberships on each OIDC login. Preserve the local
recovery administrator and back up `user.cfg` and `domains.cfg` first.
The Rauthy client `proxmox-lab2` needs `groups` added to its default scopes;
retain `openid` and `local_username`.

Grafana CT 122 runs 13.2.4. Its OAuth signup and role sync are enabled, but
`allow_assign_grafana_admin=false` and its existing role expression only maps
app-specific `grafana-admin` / `grafana-editor` roles. The proposed change
prepends `contains(groups || '[]', 'admin') && 'GrafanaAdmin' ||` to that
existing expression, sets `allow_assign_grafana_admin=true`, and appends
`groups` to OAuth scopes. Its Rauthy client already includes `groups` in the
default scopes. Back up the private config before editing; a brief Grafana
restart and fresh owner SSO are required. Other users retain the existing
role expression. Lab2 PBS CT 800 runs 4.2.8 and has automatic OIDC user
creation, but its administrator authorization still needs separate inspection.

These follow-ups have not been applied. See the upstream
[Proxmox group mapping documentation](https://github.com/proxmox/pve-docs/blob/master/pveum.adoc#groups-mapping)
and [Grafana OAuth documentation](https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/generic-oauth/).

## Acceptance and rollback

Local checks: Python camera-admin suite, Python SFTPGo hook suite and Node 24+
`node --test sso/pigallery-oidc.test.cjs`. The Node harness executes the actual
callback overlay with mocked validated token/client and account store; it does
not replace a full application type-check or live identity-provider test.
There are 30 passing local tests. Generated hunter/admin file-user records
were also accepted by installed SFTPGo 2.7.6 in an isolated SQLite provider,
without adding test identities to production. The deployed backend image was
built successfully and its JavaScript syntax checked.

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
default of `openid`; remove the extra admin callback if rolling back routing.
Restore the saved provider database or disable/remove the new admin creation
rule **before** restoring the old implicit-admin binding: leaving that rule
active with the old implicit-role setup would allow unwanted admin creation.
Stop the dedicated proxy before restoring SFTPGo's original port 8080. Do not
remove local emergency accounts or photo data.
