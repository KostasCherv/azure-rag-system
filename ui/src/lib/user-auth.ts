type HeaderSource = { get(name: string): string | null };

type ClientPrincipalClaim = { typ?: string; val?: string };

type ClientPrincipal = {
  claims?: ClientPrincipalClaim[];
};

export type UserPrincipal = {
  name: string;
  oid: string;
};

const OID_CLAIM = "http://schemas.microsoft.com/identity/claims/objectidentifier";

export function isUserAuthRequired(): boolean {
  return process.env.REQUIRE_USER_AUTH === "true";
}

// Returns the caller's user id for backend isolation, or null when user auth
// is required and no principal is present (caller should respond 401).
export function getUserId(headers: HeaderSource): string | null {
  const principal = getUserPrincipal(headers);
  if (isUserAuthRequired() && !principal) return null;
  return principal?.oid ?? "local-development-user";
}

export function getUserPrincipal(headers: HeaderSource): UserPrincipal | null {
  const encoded = headers.get("x-ms-client-principal");
  if (!encoded) return null;

  let principal: ClientPrincipal;
  try {
    principal = JSON.parse(Buffer.from(encoded, "base64").toString("utf8")) as ClientPrincipal;
  } catch {
    return null;
  }

  const claims = principal.claims;
  if (!Array.isArray(claims)) return null;

  const name = claims.find((claim) => claim.typ === "name")?.val?.trim();
  const oid = claims.find((claim) => claim.typ === OID_CLAIM)?.val?.trim();
  if (!name || !oid) return null;

  return { name, oid };
}
