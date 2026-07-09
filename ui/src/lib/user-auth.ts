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
