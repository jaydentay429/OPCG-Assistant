"use client";

import { useRouter } from "next/navigation";
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent } from "react";
import { useI18n } from "@/lib/i18n";

/** True when Enter should commit search (ignore IME composition confirm). */
export function isSearchCommitKey(e: ReactKeyboardEvent<HTMLInputElement>): boolean {
  if (e.key !== "Enter") return false;
  if (e.nativeEvent.isComposing || e.keyCode === 229) return false;
  return true;
}

export function SearchBar({
  value,
  onChange,
  onClear,
  onSubmit,
}: {
  value: string;
  onChange: (v: string) => void;
  onClear: () => void;
  /** Called when user presses Enter / Search key / 搜索 button. */
  onSubmit?: () => void;
}) {
  const { t } = useI18n();
  const router = useRouter();

  function commit(from?: HTMLInputElement | null) {
    onSubmit?.();
    from?.blur();
  }

  function onFormSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.querySelector("input");
    commit(input instanceof HTMLInputElement ? input : null);
  }

  function onInputKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (!isSearchCommitKey(e)) return;
    e.preventDefault();
    e.stopPropagation();
    commit(e.currentTarget);
  }

  return (
    <form className="search-row" onSubmit={onFormSubmit} role="search">
      <div className="search-input-wrap">
        <input
          type="search"
          name="q"
          enterKeyHint="search"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onInputKeyDown}
          onSearch={(e) => {
            e.preventDefault();
            commit(e.currentTarget);
          }}
          placeholder={t("search.placeholder")}
          aria-label={t("search.placeholder")}
        />
        {value ? (
          <button
            type="button"
            className="search-clear-btn"
            onClick={onClear}
            title={t("filter.clear")}
            aria-label={t("filter.clear")}
          >
            ×
          </button>
        ) : null}
      </div>
      <button type="submit" className="search-submit-btn">
        {t("search.submit")}
      </button>
      <button
        type="button"
        className="photo-btn photo-btn-labeled"
        title={t("search.photo_btn")}
        aria-label={t("search.photo_btn")}
        onClick={() => router.push("/photo")}
      >
        <span aria-hidden>📷</span>
        <span className="photo-btn-text">{t("search.photo_btn_short")}</span>
      </button>
    </form>
  );
}
