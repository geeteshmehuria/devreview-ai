import { describe, it, expect, beforeEach, vi } from "vitest";
import { useAuthStore } from "@/lib/stores/auth-store";

// Reset store state before each test
beforeEach(() => {
  useAuthStore.setState({
    user: null,
    isLoading: false,
    isInitialized: false,
  });
  localStorage.clear();
});

describe("AuthStore", () => {
  it("starts with no user and uninitialized", () => {
    const { user, isInitialized, isLoading } = useAuthStore.getState();
    expect(user).toBeNull();
    expect(isInitialized).toBe(false);
    expect(isLoading).toBe(false);
  });

  it("setUser updates the user state", () => {
    const mockUser = {
      id: "test-id",
      github_login: "testuser",
      github_name: "Test User",
      github_avatar_url: null,
      github_email: null,
      role: "user" as const,
    };
    useAuthStore.getState().setUser(mockUser);
    expect(useAuthStore.getState().user).toEqual(mockUser);
  });

  it("setTokens persists to localStorage", () => {
    useAuthStore.getState().setTokens("access-123", "refresh-456");
    expect(localStorage.getItem("access_token")).toBe("access-123");
    expect(localStorage.getItem("refresh_token")).toBe("refresh-456");
    // Middleware marker cookie is set, and never contains the JWT
    expect(document.cookie).toContain("session=1");
    expect(document.cookie).not.toContain("access-123");
  });

  it("clearTokens removes tokens and nulls user", () => {
    localStorage.setItem("access_token", "token");
    localStorage.setItem("refresh_token", "refresh");
    useAuthStore.setState({ user: { id: "1", github_login: "u", github_name: null, github_avatar_url: null, github_email: null, role: "user" } });

    useAuthStore.getState().clearTokens();

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(document.cookie).not.toContain("session=1");
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("initialize does nothing when no token present", async () => {
    await useAuthStore.getState().initialize();
    expect(useAuthStore.getState().isInitialized).toBe(true);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("initialize keeps the session when /auth/me fails for a non-auth reason", async () => {
    vi.doMock("@/lib/api/auth", () => ({
      authApi: { me: vi.fn().mockRejectedValue(new Error("timeout of 30000ms exceeded")) },
    }));
    localStorage.setItem("access_token", "token");
    localStorage.setItem("refresh_token", "refresh");

    await useAuthStore.getState().initialize();

    expect(localStorage.getItem("access_token")).toBe("token");
    expect(localStorage.getItem("refresh_token")).toBe("refresh");
    expect(useAuthStore.getState().isInitialized).toBe(true);
    vi.doUnmock("@/lib/api/auth");
  });
});
