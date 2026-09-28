"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { fetchMe, login as apiLogin, register as apiRegister } from "./api";
import { bindLoginOpener, clearLoginIntent, installLoginTrigger } from "./loginTrigger";
import {
  emptyAuth,
  loadStoredAuth,
  persistAuth,
  refreshAuthSession,
  restoreAuthSession,
  type AuthSnapshot,
} from "./authSession";

type AuthState = AuthSnapshot & {
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

// Register before hydrateRoot so the listener exists when __reactProps first appears.
if (typeof window !== "undefined") installLoginTrigger();

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    ...emptyAuth(),
    ready: false,
  });
  const [authOpen, setAuthOpen] = useState(false);
  // Mount, login, and logout each bump this so a late /auth/me cannot overwrite the session the user has now.
  const sessionGen = useRef(0);

  useEffect(() => {
    const generation = ++sessionGen.current;
    const stored = loadStoredAuth(localStorage);
    setState({ ...stored, ready: true });
    if (!stored.token) return;
    let cancelled = false;
    void restoreAuthSession(localStorage, {
      shouldAbort: () => cancelled || sessionGen.current !== generation,
    }).then((session) => {
      if (cancelled || sessionGen.current !== generation) return;
      setState({ ...session, ready: true });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (loginId: string, password: string) => {
    const res = await apiLogin(loginId, password);
    sessionGen.current += 1;
    let isAdmin = false;
    try {
      const me = await fetchMe(res.token);
      isAdmin = Boolean(me.is_admin);
    } catch {
      /* ignore — a blip here must not undo a successful login */
    }
    const next = {
      token: res.token,
      username: res.username,
      email: res.email,
      verified: res.email_verified,
      isAdmin,
    };
    persistAuth(localStorage, next);
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
    sessionGen.current += 1;
    persistAuth(localStorage, emptyAuth());
    setState({ ...emptyAuth(), ready: true });
  }, []);

  const refreshMe = useCallback(async () => {
    const token = state.token;
    if (!token) return;
    const generation = sessionGen.current;
    const result = await refreshAuthSession(localStorage, token, {
      shouldAbort: () => sessionGen.current !== generation,
    });
    if (sessionGen.current !== generation || result.status === "aborted") return;
    if (result.status === "updated") {
      setState({ ...result.session, ready: true });
      return;
    }
    if (result.status === "rejected") {
      setState({ ...emptyAuth(), ready: true });
      throw result.error;
    }
    throw result.error;
  }, [state.token]);

  const requestLogin = useCallback(() => setAuthOpen(true), []);
  const closeAuth = useCallback(() => setAuthOpen(false), []);

  // onClick is dropped until hydration commits. Apply a click captured before that.
  useLayoutEffect(() => bindLoginOpener(requestLogin), [requestLogin]);
  useLayoutEffect(() => {
    if (authOpen) clearLoginIntent();
  }, [authOpen]);

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
