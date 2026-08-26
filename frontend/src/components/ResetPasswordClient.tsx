"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { resetPassword } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { PasswordField } from "./PasswordField";

export function ResetPasswordClient() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const token = useMemo(() => String(searchParams.get("token") || "").trim(), [searchParams]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token) {
      setError(t("auth.reset_missing_token"));
      return;
    }
    const fd = new FormData(e.currentTarget);
    const pwd = String(fd.get("password") || "");
    const pwd2 = String(fd.get("password2") || "");
    if (pwd !== pwd2) {
      setError(t("auth.password_mismatch"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await resetPassword(token, pwd);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack auth-reset-page">
      <h1 className="page-title">{t("auth.reset_title")}</h1>
      <p className="muted">{t("auth.reset_subtitle")}</p>

      {!token ? (
        <div className="deck-panel">
          <p className="error">{t("auth.reset_missing_token")}</p>
          <p className="muted">{t("auth.reset_request_again")}</p>
        </div>
      ) : done ? (
        <div className="deck-panel">
          <p className="auth-info">{t("auth.reset_ok")}</p>
          <Link href="/" className="secondary" style={{ display: "inline-block", textDecoration: "none" }}>
            {t("auth.back_home")}
          </Link>
        </div>
      ) : (
        <form className="deck-panel fields auth-reset-form" onSubmit={onSubmit}>
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
            {busy ? t("auth.reset_saving") : t("auth.reset_submit")}
          </button>
          {error ? <p className="error">{error}</p> : null}
        </form>
      )}
    </div>
  );
}
