"use client";

import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

/** Login CTA used on gated pages (collector / binder). */
export function LoginGate({ title, body }: { title: string; body: string }) {
  const { t } = useI18n();
  const { requestLogin } = useAuth();

  return (
    <div className="deck-panel login-gate">
      <h2 className="deck-section-title">{title}</h2>
      <p className="muted login-gate-body">{body}</p>
      <button type="button" onClick={() => requestLogin()}>
        {t("auth.login")}
      </button>
    </div>
  );
}
