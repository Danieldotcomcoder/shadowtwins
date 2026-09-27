import { afterEach, describe, expect, it } from "vitest";
import { adoptTokenFromUrl, getOperatorToken, setOperatorToken, tokenFromHash } from "./client";

describe("login-link token", () => {
  afterEach(() => {
    setOperatorToken(null);
    window.history.replaceState(null, "", "/");
  });

  it("parses the token from a URL fragment", () => {
    expect(tokenFromHash("#token=abc-DEF_123")).toBe("abc-DEF_123");
    expect(tokenFromHash("#x=1&token=a%2Bb")).toBe("a+b");
    expect(tokenFromHash("#other=1")).toBeNull();
    expect(tokenFromHash("")).toBeNull();
    expect(tokenFromHash("#token=")).toBeNull();
  });

  it("adopts the token once, remembers it, and removes it from the address bar", () => {
    window.history.replaceState(null, "", "/runs?x=1#token=secret-123");
    expect(adoptTokenFromUrl()).toBe(true);
    expect(getOperatorToken()).toBe("secret-123");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname + window.location.search).toBe("/runs?x=1");
    expect(adoptTokenFromUrl()).toBe(false);
    expect(getOperatorToken()).toBe("secret-123");
  });
});
