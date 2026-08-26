const ALLOW_KEY = "opcg_battle_allow_spectators_default";
const HANDS_KEY = "opcg_battle_show_hands_default";

export type BattleSpectatorPrefs = {
  allowSpectators: boolean;
  showHands: boolean;
};

export function readBattleSpectatorPrefs(): BattleSpectatorPrefs {
  if (typeof window === "undefined") {
    return { allowSpectators: true, showHands: true };
  }
  try {
    const allow = localStorage.getItem(ALLOW_KEY);
    const hands = localStorage.getItem(HANDS_KEY);
    return {
      allowSpectators: allow == null ? true : allow === "1",
      showHands: hands == null ? true : hands === "1",
    };
  } catch {
    return { allowSpectators: true, showHands: true };
  }
}

export function saveBattleSpectatorPrefs(prefs: BattleSpectatorPrefs) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(ALLOW_KEY, prefs.allowSpectators ? "1" : "0");
    localStorage.setItem(HANDS_KEY, prefs.showHands ? "1" : "0");
  } catch {
    /* ignore */
  }
}
