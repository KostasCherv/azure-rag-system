import { afterEach, describe, expect, it } from "vitest";
import { getUserId, getUserPrincipal, isUserAuthRequired } from "./user-auth";

function encodePrincipal(claims: Array<{ typ: string; val: string }>): string {
  return Buffer.from(JSON.stringify({ auth_typ: "aad", claims }), "utf8").toString("base64");
}

describe("user auth", () => {
  afterEach(() => {
    delete process.env.REQUIRE_USER_AUTH;
  });

  it("requires auth only when REQUIRE_USER_AUTH is true", () => {
    expect(isUserAuthRequired()).toBe(false);
    process.env.REQUIRE_USER_AUTH = "false";
    expect(isUserAuthRequired()).toBe(false);
    process.env.REQUIRE_USER_AUTH = "true";
    expect(isUserAuthRequired()).toBe(true);
  });

  it("parses name and oid from x-ms-client-principal", () => {
    const headers = new Headers({
      "x-ms-client-principal": encodePrincipal([
        { typ: "name", val: "Ada Lovelace" },
        {
          typ: "http://schemas.microsoft.com/identity/claims/objectidentifier",
          val: "11111111-1111-1111-1111-111111111111",
        },
      ]),
    });
    expect(getUserPrincipal(headers)).toEqual({
      name: "Ada Lovelace",
      oid: "11111111-1111-1111-1111-111111111111",
    });
  });

  it("resolves the user id from the principal, with a local fallback", () => {
    const headers = new Headers({
      "x-ms-client-principal": encodePrincipal([
        { typ: "name", val: "Ada Lovelace" },
        {
          typ: "http://schemas.microsoft.com/identity/claims/objectidentifier",
          val: "11111111-1111-1111-1111-111111111111",
        },
      ]),
    });
    expect(getUserId(headers)).toBe("11111111-1111-1111-1111-111111111111");
    expect(getUserId(new Headers())).toBe("local-development-user");
    process.env.REQUIRE_USER_AUTH = "true";
    expect(getUserId(headers)).toBe("11111111-1111-1111-1111-111111111111");
    expect(getUserId(new Headers())).toBeNull();
  });

  it("returns null when the principal header is missing or malformed", () => {
    expect(getUserPrincipal(new Headers())).toBeNull();
    expect(getUserPrincipal(new Headers({ "x-ms-client-principal": "not-base64-json" }))).toBeNull();
    expect(
      getUserPrincipal(
        new Headers({
          "x-ms-client-principal": encodePrincipal([{ typ: "name", val: "Ada Lovelace" }]),
        }),
      ),
    ).toBeNull();
  });
});
