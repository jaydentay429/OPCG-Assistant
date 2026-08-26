"use client";

import { FormEvent, useState } from "react";
import { forgotPassword } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { PasswordField } from "./PasswordField";

type AuthTab = "login" | "register" | "forgot";

export function AuthModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const { login, register } = useAuth();
  const [tab, setTab] = useState<AuthTab>("login");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  function switchTab(next: AuthTab) {
    setTab(next);
    setError("");
    setInfo("");
  }

  async function onLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    setInfo("");
    try {
      await login(String(fd.get("login") || ""), String(fd.get("password") || ""));
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRegister(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const pwd = String(fd.get("password") || "");
    const pwd2 = String(fd.get("password2") || "");
    if (pwd !== pwd2) {
      setError(t("auth.password_mismatch"));
      return;
    }
    setBusy(true);
    setError("");
    setInfo("");
    try {
      await register(String(fd.get("email") || ""), String(fd.get("username") || ""), pwd);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onForgot(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    setInfo("");
    try {
      const res = await forgotPassword(String(fd.get("email") || ""));
      setInfo(res.message || t("auth.forgot_sent"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const title =
    tab === "login" ? t("auth.login") : tab === "register" ? t("auth.register") : t("auth.forgot_title");

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog">
        <h2>{title}</h2>
        {tab !== "forgot" ? (
          <div className="tabs">
            <button type="button" className={tab === "login" ? undefined : "secondary"} onClick={() => switchTab("login")}>
              {t("auth.login")}
            </button>
            <button
              type="button"
              className={tab === "register" ? undefined : "secondary"}
              onClick={() => switchTab("register")}
            >
              {t("auth.register")}
            </button>
          </div>
        ) : null}

        {tab === "login" ? (
          <form className="fields" onSubmit={onLogin}>
            <input name="login" placeholder={t("auth.email_or_user")} required autoComplete="username" />
            <PasswordField
              name="password"
              placeholder={t("auth.password")}
              required
              autoComplete="current-password"
            />
            <button type="submit" disabled={busy}>
              {t("auth.login")}
            </button>
            <button type="button" className="ghost auth-forgot-link" onClick={() => switchTab("forgot")}>
              {t("auth.forgot_link")}
            </button>
          </form>
        ) : null}

        {tab === "register" ? (
          <form className="fields" onSubmit={onRegister}>
            <input name="email" type="email" placeholder={t("auth.email")} required autoComplete="email" />
            <input name="username" placeholder={t("auth.username")} required autoComplete="username" />
            <PasswordField
              name="password"
              placeholder={t("auth.password_min")}
              required
              minLength={8}
              autoComplete="new-password"
            />
            <PasswordField
              name="password2"
              placeholder={t("auth.password_confirm")}
              required
              minLength={8}
              autoComplete="new-password"
            />
            <button type="submit" disabled={busy}>
              {t("auth.register")}
            </button>
          </form>
        ) : null}

        {tab === "forgot" ? (
          <form className="fields" onSubmit={onForgot}>
            <p className="muted auth-forgot-hint">{t("auth.forgot_hint")}</p>
            <input name="email" type="email" placeholder={t("auth.email")} required autoComplete="email" />
            <button type="submit" disabled={busy}>
              {busy ? t("auth.forgot_sending") : t("auth.forgot_submit")}
            </button>
            <button type="button" className="ghost auth-forgot-link" onClick={() => switchTab("login")}>
              {t("auth.back_to_login")}
            </button>
          </form>
        ) : null}

        {info ? <p className="auth-info">{info}</p> : null}
        {error ? <p className="error">{error}</p> : null}
        <button type="button" className="ghost" style={{ marginTop: 8, width: "100%" }} onClick={onClose}>
          {t("deck.save_cancel")}
        </button>
      </div>
    </div>
  );
}
