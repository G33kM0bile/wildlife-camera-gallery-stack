"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.OIDCAuthService = void 0;
const Config_1 = require("../../../common/config/private/Config");
const openid_client_1 = require("openid-client");
const UserDTO_1 = require("../../../common/entities/UserDTO");
const Error_1 = require("../../../common/entities/Error");
const ObjectManagers_1 = require("../../model/ObjectManagers");
const crypto_1 = require("crypto");
const WildlifeGroupPolicy_1 = require("./WildlifeGroupPolicy");
class OIDCAuthService {
    static clientPromise = null;
    static async login(req, res) {
        const client = await this.getClient();
        const state = openid_client_1.generators.state();
        const verifier = openid_client_1.generators.codeVerifier();
        const challenge = openid_client_1.generators.codeChallenge(verifier);
        req.session.oidc = {
            state,
            verifier
        };
        const authUrl = client.authorizationUrl({
            scope: Config_1.Config.Users.oidc.scopes.join(' '),
            state,
            code_challenge: challenge,
            code_challenge_method: 'S256'
        });
        res.redirect(authUrl);
    }
    static async callback(req, res) {
        const storedOidc = req.session.oidc;
        const params = req.query; // code, state
        if (!storedOidc?.state || params.state !== storedOidc?.state) {
            throw new Error_1.ErrorDTO(Error_1.ErrorCodes.GENERAL_ERROR, 'Invalid OIDC state');
        }
        const client = await this.getClient();
        const tokenSet = await client.callback(Config_1.Config.Users.oidc.redirectUri, params, {
            state: storedOidc?.state,
            code_verifier: storedOidc?.verifier
        });
        const claims = tokenSet.claims();
        const groupAuth = process.env.PIGALLERY_OIDC_GROUP_AUTH === '1';
        // Reject before lookup or account creation. Admin takes precedence.
        const groupRole = groupAuth
            ? ((0, WildlifeGroupPolicy_1.wildlifeAccess)(claims.groups) === 'admin' ? UserDTO_1.UserRoles.Admin : UserDTO_1.UserRoles.User)
            : null;
        const usernameClaim = Config_1.Config.Users.oidc.usernameClaim || 'preferred_username';
        const emailClaim = Config_1.Config.Users.oidc.emailClaim || 'email';
        const preferredUserName = claims[usernameClaim] || (groupAuth ? claims.preferred_username : '') || '';
        const email = claims[emailClaim] || '';
        const matchedName = (preferredUserName || (email ? String(email).split('@')[0] : '')).toString();
        if (groupAuth && (typeof preferredUserName !== 'string' || !preferredUserName.trim())) {
            throw new Error_1.ErrorDTO(Error_1.ErrorCodes.CREDENTIAL_NOT_FOUND, 'OIDC: missing stable username');
        }
        if (!matchedName) {
            throw new Error_1.ErrorDTO(Error_1.ErrorCodes.CREDENTIAL_NOT_FOUND, 'OIDC: missing username/email');
        }
        // domain allow-list if configured
        if (Config_1.Config.Users.oidc.allowedDomains && Config_1.Config.Users.oidc.allowedDomains.length > 0 && email) {
            const domain = String(email).split('@')[1] || '';
            const allowed = Config_1.Config.Users.oidc.allowedDomains.some(d => d.toLowerCase() === domain.toLowerCase());
            if (!allowed) {
                throw new Error_1.ErrorDTO(Error_1.ErrorCodes.CREDENTIAL_NOT_FOUND, `Email domain not allowed: ${domain}`);
            }
        }
        // try find user by name
        let user = await ObjectManagers_1.ObjectManagers.getInstance().UserManager.findOne({ name: matchedName });
        if (!user && Config_1.Config.Users.oidc.autoCreateUser) {
            const rnd = (0, crypto_1.randomBytes)(48).toString('base64url');
            const newUser = { name: matchedName, password: rnd, role: groupRole ?? UserDTO_1.UserRoles.Guest };
            user = await ObjectManagers_1.ObjectManagers.getInstance().UserManager.createUser(newUser);
        }
        if (!user) {
            throw new Error_1.ErrorDTO(Error_1.ErrorCodes.CREDENTIAL_NOT_FOUND, 'User not found');
        }
        if (groupRole !== null && user.role !== groupRole) {
            user = await ObjectManagers_1.ObjectManagers.getInstance().UserManager.changeRole(user.id, groupRole);
        }
        if (groupRole === UserDTO_1.UserRoles.Admin) {
            // Global admins must not inherit a previous per-user gallery projection.
            user = { ...user, overrideAllowBlockList: true, allowQuery: null, blockQuery: null };
        }
        req.session.context = await ObjectManagers_1.ObjectManagers.getInstance().SessionManager.buildContext(user);
        req.session.rememberMe = true;
        // cleanup
        delete req.session.oidc;
        // redirect to root or previously stored path
        res.redirect('/');
    }
    static async getClient() {
        if (this.clientPromise) {
            return this.clientPromise;
        }
        if (!Config_1.Config.Users.oidc.enabled) {
            throw new Error('OIDC is not enabled');
        }
        const issuerUrl = Config_1.Config.Users.oidc.issuerUrl;
        if (!issuerUrl) {
            throw new Error('OIDC issuerUrl is not configured');
        }
        this.clientPromise = (async () => {
            const issuer = await openid_client_1.Issuer.discover(issuerUrl);
            return new issuer.Client({
                client_id: Config_1.Config.Users.oidc.clientId,
                client_secret: Config_1.Config.Users.oidc.clientSecret,
                redirect_uris: [Config_1.Config.Users.oidc.redirectUri],
                response_types: ['code']
            });
        })();
        return this.clientPromise;
    }
}
exports.OIDCAuthService = OIDCAuthService;
