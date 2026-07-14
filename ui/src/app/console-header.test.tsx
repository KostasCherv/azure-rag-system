// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ConsoleHeader } from "./console-header";

afterEach(() => cleanup());

const principal = { name: "Ada Lovelace", oid: "oid-123" };

describe("ConsoleHeader", () => {
  it("renders the user name and sign-out link on the chat variant", () => {
    render(<ConsoleHeader title="Chat" variant="chat" principal={principal} />);
    expect(screen.getByText("Ada Lovelace")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Switch account" }).getAttribute("href")).toBe(
      "/.auth/logout?post_logout_redirect_uri=%2F.auth%2Flogin%2Faad%3Fpost_login_redirect_uri%3D%2F",
    );
    expect(screen.getByRole("link", { name: "Sign out" }).getAttribute("href")).toBe("/.auth/logout");
  });

  it("renders the user name and sign-out link on the corpus variant", () => {
    render(<ConsoleHeader title="Corpus" variant="corpus" principal={principal} />);
    expect(screen.getByText("Ada Lovelace")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Switch account" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sign out" }).getAttribute("href")).toBe("/.auth/logout");
  });

  it("renders no sign-out link without a principal", () => {
    render(<ConsoleHeader title="Chat" variant="chat" />);
    expect(screen.queryByRole("link", { name: "Switch account" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Sign out" })).toBeNull();
  });
});
