// Called only with claims from openid-client's validated ID token.
export function wildlifeAccess(groups: unknown): 'admin' | 'hunter' {
  if (!Array.isArray(groups) || !groups.every(group => typeof group === 'string')) {
    throw new Error('OIDC: missing or malformed groups');
  }
  if (groups.includes('admin')) {
    return 'admin';
  }
  if (groups.includes('hunters')) {
    return 'hunter';
  }
  throw new Error('OIDC: wildlife group membership required');
}
