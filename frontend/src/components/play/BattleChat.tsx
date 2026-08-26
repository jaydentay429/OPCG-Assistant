"use client";

import { useEffect, useRef, useState } from "react";
import type { BattleChatMessage } from "@/lib/battleWs";
import { useI18n } from "@/lib/i18n";

type Props = {
  messages: BattleChatMessage[];
  selfUserId?: string | null;
  readOnly?: boolean;
  onSend?: (text: string) => void;
};

export function BattleChat({ messages, selfUserId, readOnly = false, onSend }: Props) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  function submit() {
    const text = draft.trim();
    if (!text || readOnly || !onSend) return;
    onSend(text);
    setDraft("");
  }

  return (
    <div className="ux-chat">
      <div className="ux-rail-title">{t("play.chat_title")}</div>
      <div className="ux-chat-list" ref={listRef}>
        {messages.length ? (
          messages.map((msg) => {
            const mine = Boolean(selfUserId && msg.user_id === selfUserId);
            return (
              <div key={msg.id} className={`ux-chat-line ${mine ? "is-mine" : ""}`}>
                <span className="ux-chat-name">{msg.username}</span>
                <span className="ux-chat-text">{msg.text}</span>
              </div>
            );
          })
        ) : (
          <div className="ux-chat-line muted">{t("play.chat_empty")}</div>
        )}
      </div>
      {readOnly || !onSend ? (
        <p className="ux-chat-readonly muted">{t("play.chat_readonly")}</p>
      ) : (
        <form
          className="ux-chat-form"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <input
            className="ux-chat-input"
            value={draft}
            maxLength={200}
            placeholder={t("play.chat_placeholder")}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" className="secondary ux-chat-send" disabled={!draft.trim()}>
            {t("play.chat_send")}
          </button>
        </form>
      )}
    </div>
  );
}
