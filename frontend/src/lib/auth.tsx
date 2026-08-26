"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchMe, login as apiLogin, register as apiRegister } from "./api";
import type { MeResponse } from "./types";

const AUTH_KEY = "opcg_auth_mirror_v1";

type AuthState = {
  token: string | null;
  username: string | null;
  email: string | null;
  verified: boolean;
  isAdmin: boolean;
  ready: boolean;
};

type AuthCtx = AuthState & {
  isLoggedIn: boolean;
  login: (loginId: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
  requestLogin: () => void;
  closeAuth: () => void;
  authOpen: boolean;
};

const Ctx = createContext<AuthCtx | null>(null);

function loadStored(): Omit<AuthState, "ready"> {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return { token: null, username: null, email: null, verified: false, isAdmin: false };
    const data = JSON.parse(raw) as { t?: string; u?: string; e?: string; v?: string; a?: string };
    if (!data?.t) return { token: null, username: null, email: null, verified: false, isAdmin: false };
    return {
      token: data.t,
      username: data.u || null,
      email: data.e || null,
      verified: data.v === "1",
      isAdmin: data.a === "1",
    };
  } catch {
    return { token: null, username: null, email: null, verified: false, isAdmin: false };
  }
}

function persist(s: Omit<AuthState, "ready">) {
  try {
    if (!s.token) {
      localStorage.removeItem(AUTH_KEY);
      return;
    }
    localStorage.setItem(
      AUTH_KEY,
      JSON.stringify({
        t: s.token,
        u: s.username || "",
        e: s.email || "",
        v: s.verified ? "1" : "0",
        a: s.isAdmin ? "1" : "0",
      }),
    );
  } catch {
    /* ignore */
  }
}

function fromMe(token: string, me: MeResponse): Omit<AuthState, "ready"> {
  return {
    token,
    username: me.username,
    email: me.email,
    verified: me.email_verified,
    isAdmin: Boolean(me.is_admin),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    username: null,
    email: null,
    verified: false,
    isAdmin: false,
    ready: false,
  });
  const [authOpen, setAuthOpen] = useState(false);

  useEffect(() => {
    const stored = loadStored();
    setState({ ...stored, ready: true });
    if (stored.token) {
      fetchMe(stored.token)
        .then((me: MeResponse) => {
          const next = fromMe(stored.token!, me);
          setState({ ...next, ready: true });
          persist(next);
        })
        .catch(() => {
          persist({ token: null, username: null, email: null, verified: false, isAdmin: false });
          setState({
            token: null,
            username: null,
            email: null,
            verified: false,
            isAdmin: false,
            ready: true,
          });
        });
    }
  }, []);

  const login = useCallback(async (loginId: string, password: string) => {
    const res = await apiLogin(loginId, password);
    let isAdmin = false;
    try {
      const me = await fetchMe(res.token);
      isAdmin = Boolean(me.is_admin);
    } catch {
      /* ignore */
    }
    const next = {
      token: res.token,
      username: res.username,
      email: res.email,
      verified: res.email_verified,
      isAdmin,
    };
    persist(next);
    setState({ ...next, ready: true });
    setAuthOpen(false);
  }, []);

  const register = useCallback(
    async (email: string, username: string, password: string) => {
      await apiRegister(email, username, password);
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    persist({ token: null, username: null, email: null, verified: false, isAdmin: false });
    setState({
      token: null,
      username: null,
      email: null,
      verified: false,
      isAdmin: false,
      ready: true,
    });
  }, []);

  const refreshMe = useCallback(async () => {
    if (!state.token) return;
    const me = await fetchMe(state.token);
    const next = fromMe(state.token, me);
    persist(next);
    setState({ ...next, ready: true });
  }, [state.token]);

  const requestLogin = useCallback(() => setAuthOpen(true), []);
  const closeAuth = useCallback(() => setAuthOpen(false), []);

  const value = useMemo(
    () => ({
      ...state,
      isLoggedIn: Boolean(state.token),
      login,
      register,
      logout,
      refreshMe,
      requestLogin,
      closeAuth,
      authOpen,
    }),
    [state, login, register, logout, refreshMe, requestLogin, closeAuth, authOpen],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
