import raw from "@/generated/card-editor-notes.json";

type NoteMap = Record<string, string>;

const NOTES = raw as NoteMap;

/** Optional editor note for a card id. Empty / missing ids return null (do not invent copy). */
export function cardEditorNote(cardId: string): string | null {
  const text = String(NOTES[cardId] || NOTES[cardId.split("-P")[0]] || "").trim();
  return text || null;
}
