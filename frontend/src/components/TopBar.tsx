"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { submitBattleBugReport } from "@/lib/api";
import { useI18n, type Lang } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

export function TopBar() {
  const { t, lang, setLang } = useI18n();
  const { isLoggedIn, username, token, logout, requestLogin } = useAuth();
  const [zhMenuOpen, setZhMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [bugOpen, setBugOpen] = useState(false);
  const [bugText, setBugText] = useState("");
  const [bugBusy, setBugBusy] = useState(false);
  const [bugStatus, setBugStatus] = useState("");
  const zhMenuRef = useRef<HTMLDivElement | null>(null);
  const userMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!zhMenuOpen && !userMenuOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target;
      if (!(target instanceof Node)) return;
      if (zhMenuOpen && zhMenuRef.current && !zhMenuRef.current.contains(target)) {
        setZhMenuOpen(false);
      }
      if (userMenuOpen && userMenuRef.current && !userMenuRef.current.contains(target)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [zhMenuOpen, userMenuOpen]);

  function pickChinese(next: Lang) {
    setLang(next);
    setZhMenuOpen(false);
  }

  function openBug() {
    if (!isLoggedIn || !token) {
      requestLogin();
      return;
    }
    setBugStatus("");
    setBugOpen(true);
  }

  async function submitBug() {
    if (!token) {
      requestLogin();
      return;
    }
    const msg = bugText.trim();
    if (msg.length < 4) {
      setBugStatus(t("app.bug_too_short"));
      return;
    }
    setBugBusy(true);
    setBugStatus("");
    try {
      await submitBattleBugReport(token, {
        message: msg,
        page_url: typeof window !== "undefined" ? window.location.href : null,
      });
      setBugStatus(t("app.bug_sent"));
      setBugText("");
      window.setTimeout(() => {
        setBugOpen(false);
        setBugStatus("");
      }, 900);
    } catch (e) {
      setBugStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setBugBusy(false);
    }
  }

  return (
    <>
      <header className="top-bar">
        <Link href="/" className="brand">
          {t("app.page_title")}
        </Link>
        <div className="actions">
          <button type="button" className="ghost topbar-bug-btn" onClick={openBug}>
            {t("app.bug_report")}
          </button>
          {lang === "en" ? (
            <div className="lang-menu" ref={zhMenuRef}>
              <button
                type="button"
                className="secondary"
                aria-expanded={zhMenuOpen}
                aria-haspopup="menu"
                onClick={() => {
                  setUserMenuOpen(false);
                  setZhMenuOpen((v) => !v);
                }}
              >
                {t("lang.to_zh")}
              </button>
              {zhMenuOpen ? (
                <div className="lang-menu-panel" role="menu">
                  <button type="button" role="menuitem" onClick={() => pickChinese("zh-Hant")}>
                    {t("lang.zh_hant")}
                  </button>
                  <button type="button" role="menuitem" onClick={() => pickChinese("zh-Hans")}>
                    {t("lang.zh_hans")}
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <button type="button" className="secondary" onClick={() => setLang("en")}>
              {t("lang.to_en")}
            </button>
          )}
          {isLoggedIn ? (
            <div className="lang-menu user-menu" ref={userMenuRef}>
              <button
                type="button"
                className="ghost"
                title={username || ""}
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
                onClick={() => {
                  setZhMenuOpen(false);
                  setUserMenuOpen((v) => !v);
                }}
              >
                {username || t("auth.guest")}
              </button>
              {userMenuOpen ? (
                <div className="lang-menu-panel" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    className="user-menu-logout"
                    onClick={() => {
                      setUserMenuOpen(false);
                      logout();
                    }}
                  >
                    {t("auth.logout")}
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <button type="button" onClick={() => requestLogin()}>
              {t("auth.login")}
            </button>
          )}
        </div>
      </header>
      <div className="sponsor">
        <strong>{t("sponsor.title")}</strong> · {t("sponsor.desc")}{" "}
        <a href="mailto:jaydentay429@gmail.com">jaydentay429@gmail.com</a>
      </div>

      {bugOpen ? (
        <div
          className="deck-details-backdrop topbar-bug-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !bugBusy) setBugOpen(false);
          }}
        >
          <section className="deck-import-modal topbar-bug-modal" role="dialog" aria-modal="true" aria-labelledby="topbar-bug-title">
            <div className="deck-details-head">
              <h2 id="topbar-bug-title">{t("app.bug_title")}</h2>
              <button
                type="button"
                className="ghost"
                disabled={bugBusy}
                onClick={() => setBugOpen(false)}
                aria-label={t("app.bug_close")}
              >
                ×
              </button>
            </div>
            <p className="muted deck-import-hint">{t("app.bug_hint")}</p>
            <textarea
              className="deck-import-textarea topbar-bug-textarea"
              rows={5}
              value={bugText}
              onChange={(e) => setBugText(e.target.value)}
              placeholder={t("app.bug_placeholder")}
              disabled={bugBusy}
            />
            {bugStatus ? (
              <p className={bugStatus === t("app.bug_sent") ? "muted" : "error-text"}>{bugStatus}</p>
            ) : null}
            <div className="deck-details-actions">
              <button type="button" className="secondary" disabled={bugBusy} onClick={() => setBugOpen(false)}>
                {t("app.bug_close")}
              </button>
              <button type="button" disabled={bugBusy} onClick={() => void submitBug()}>
                {bugBusy ? t("app.bug_sending") : t("app.bug_submit")}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
