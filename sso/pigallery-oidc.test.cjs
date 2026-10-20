const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {stripTypeScriptTypes} = require('node:module');
const {randomBytes} = require('node:crypto');

const sourceDir = path.join(__dirname, '../pigallery2-map/overlay/src/backend/middlewares/user');
function loadSource(name, bindings, exportName) {
  const ts = fs.readFileSync(path.join(sourceDir, name), 'utf8');
  const js = stripTypeScriptTypes(ts).replace(/^import .*;\r?\n/gm, '')
    .replace(/^export /gm, '') + `\nmodule.exports = ${exportName};`;
  const sandbox = {...bindings, module: {exports: {}}};
  vm.runInNewContext(js, sandbox, {filename: name});
  return sandbox.module.exports;
}
const wildlifeAccess = loadSource('WildlifeGroupPolicy.ts', {}, 'wildlifeAccess');

function harness(claims, existing = null, autoCreateUser = true) {
  const changes = [];
  const manager = {
    findOne: async () => existing,
    createUser: async user => {changes.push(['create', user]); return {...user, id: 42};},
    changeRole: async (id, role) => {changes.push(['role', role]); return {...existing, id, role};}
  };
  const client = {callback: async () => ({claims: () => claims})};
  const roles = {Guest: 2, User: 3, Admin: 4};
  const service = loadSource('OIDCAuthService.ts', {
    Config: {Users: {oidc: {enabled: true, issuerUrl: 'https://idp.test', scopes: ['openid', 'groups'],
      usernameClaim: 'local_username', autoCreateUser}}},
    process: {env: {PIGALLERY_OIDC_GROUP_AUTH: '1'}},
    Issuer: {discover: async () => ({Client: function () {return client;}})},
    ObjectManagers: {getInstance: () => ({UserManager: manager,
      SessionManager: {buildContext: async user => ({user})}})},
    UserRoles: roles, ErrorDTO: Error, ErrorCodes: {CREDENTIAL_NOT_FOUND: 'denied'},
    randomBytes, wildlifeAccess
  }, 'OIDCAuthService');
  const req = {session: {oidc: {state: 'expected', verifier: 'verifier'}}, query: {state: 'expected'}};
  const res = {redirect: url => changes.push(['redirect', url])};
  return {service, req, res, changes};
}

test('missing, malformed, case-changed and prefix groups cannot create accounts', async () => {
  for (const groups of [undefined, 'hunters', [], ['Hunters'], ['hunters-other'], ['hunters', 123]]) {
    const h = harness({preferred_username: 'new-user', groups});
    await assert.rejects(h.service.callback(h.req, h.res));
    assert.equal(h.changes.length, 0);
    assert.equal(h.req.session.context, undefined);
  }
});
test('hunters auto-create as regular users with strong random passwords', async () => {
  const h = harness({preferred_username: 'new-user', groups: ['hunters']});
  await h.service.callback(h.req, h.res);
  assert.equal(h.req.session.context.user.role, 3);
  assert.equal(h.changes[0][1].name, 'new-user');
  assert.equal(h.changes[0][1].password.length, 64);
  assert.equal(h.req.session.oidc, undefined);
});
test('admin wins over hunters and has no gallery projection', async () => {
  const h = harness({local_username: 'ExistingName', groups: ['hunters', 'admin']},
    {id: 4, name: 'ExistingName', role: 3, overrideAllowBlockList: true, allowQuery: {restricted: true}});
  await h.service.callback(h.req, h.res);
  assert.equal(h.req.session.context.user.role, 4);
  assert.equal(h.req.session.context.user.allowQuery, null);
  assert.equal(h.req.session.context.user.blockQuery, null);
});
test('removing admin membership demotes the local role on the next login', async () => {
  const h = harness({local_username: 'ExistingName', groups: ['hunters']},
    {id: 4, name: 'ExistingName', role: 4});
  await h.service.callback(h.req, h.res);
  assert.equal(h.req.session.context.user.role, 3);
});
test('no username and auto-creation disabled both deny new accounts', async () => {
  for (const h of [harness({email: 'user@example.test', groups: ['hunters']}),
    harness({preferred_username: 'new-user', groups: ['hunters']}, null, false)]) {
    await assert.rejects(h.service.callback(h.req, h.res));
    assert.equal(h.changes.length, 0);
  }
});
test('removing all allowed groups denies even an existing admin account', async () => {
  const h = harness({local_username: 'ExistingName', groups: []}, {id: 4, role: 4});
  await assert.rejects(h.service.callback(h.req, h.res));
  assert.equal(h.changes.length, 0);
});
