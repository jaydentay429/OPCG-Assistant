"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import {
  readBattleSpectatorPrefs,
  saveBattleSpectatorPrefs,
  type BattleSpectatorPrefs,
} from "@/lib/battleSpectatorPrefs";

type Props = {
  prefs: BattleSpectatorPrefs;
  onChange: (prefs: BattleSpectatorPrefs) => void;
  disabled?: boolean;
};

export function SpectatorPrefsToggles({ prefs, onChange, disabled = false }: Props) {
  const { t } = useI18n();
  return (
    <div className="play-spectator-prefs">
      <label className="play-check">
        <input
          type="checkbox"
          checked={prefs.allowSpectators}
          disabled={disabled}
          onChange={(e) => {
            const next = { ...prefs, allowSpectators: e.target.checked };
            onChange(next);
            saveBattleSpectatorPrefs(next);
          }}
        />
        <span>{t("play.spectator_allow")}</span>
      </label>
      <label className="play-check">
        <input
          type="checkbox"
          checked={prefs.showHands}
          disabled={disabled || !prefs.allowSpectators}
          onChange={(e) => {
            const next = { ...prefs, showHands: e.target.checked };
            onChange(next);
            saveBattleSpectatorPrefs(next);
          }}
        />
        <span>{t("play.spectator_show_hands")}</span>
      </label>
    </div>
  );
}

export function useSpectatorPrefs() {
  const [prefs, setPrefs] = useState<BattleSpectatorPrefs>(() => readBattleSpectatorPrefs());
  return { prefs, setPrefs };
}
