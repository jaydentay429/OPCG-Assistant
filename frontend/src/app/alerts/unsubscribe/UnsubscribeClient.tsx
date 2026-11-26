"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { unsubscribeCardAlerts } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function Inner() {
  const { t } = useI18n();
  const token = useSearchParams().get("token") || "";
  const [state, setState] = useState<"idle" | "busy" | "done" | "invalid">(token ? "idle" : "invalid");

  async function run() {
    setState("busy");
    try {
      await unsubscribeCardAlerts(token);
      setState("done");
    } catch {
      setState("invalid");
    }
  }

  return (
    <div className="deck-panel stack">
      <h1 className="deck-section-title">{t("alerts.unsub_title")}</h1>
      {state === "done" ? <p role="status">{t("alerts.unsub_done")}</p> : null}
      {state === "invalid" ? <p role="status">{t("alerts.unsub_invalid")}</p> : null}
      {state === "idle" || state === "busy" ? (
        <>
          <p className="muted">{t("alerts.unsub_desc")}</p>
          <button type="button" className="btn-danger" disabled={state === "busy"} onClick={() => void run()}>
            {t("alerts.unsub_button")}
          </button>
        </>
      ) : null}
    </div>
  );
}

export function UnsubscribeClient() {
  return (
    <Suspense fallback={null}>
      <Inner />
    </Suspense>
  );
}
