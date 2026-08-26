"use client";
import { useI18n } from "@/lib/i18n";

type Props = {
  frameIndex: number;
  frameCount: number;
  onJump: (kind: "first" | "last") => void;
  onStep: (delta: number) => void;
  onSeek: (index: number) => void;
  perspective: 0 | 1;
  onPerspectiveChange: (seat: 0 | 1) => void;
  p0Name: string;
  p1Name: string;
};

export function ReplayControls({
  frameIndex,
  frameCount,
  onJump,
  onStep,
  onSeek,
  perspective,
  onPerspectiveChange,
  p0Name,
  p1Name,
}: Props) {
  const { t } = useI18n();
  const maxIndex = Math.max(0, frameCount - 1);

  return (
    <div className="replay-controls" role="toolbar" aria-label={t("play.replay_controls")}>
      <div className="replay-controls-nav">
        <button type="button" className="secondary" disabled={frameIndex <= 0} onClick={() => onJump("first")}>⏮</button>
        <button type="button" className="secondary" disabled={frameIndex <= 0} onClick={() => onStep(-1)}>◀</button>
        <span className="replay-frame-label">{frameIndex + 1}/{frameCount}</span>
        <button type="button" className="secondary" disabled={frameIndex >= maxIndex} onClick={() => onStep(1)}>▶</button>
        <button type="button" className="secondary" disabled={frameIndex >= maxIndex} onClick={() => onJump("last")}>⏭</button>
      </div>
      <input
        type="range"
        className="replay-scrubber"
        min={0}
        max={maxIndex}
        value={frameIndex}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label={t("play.replay_scrub")}
      />
      <label className="replay-perspective">
        <span>{t("play.replay_perspective")}</span>
        <select
          className="replay-perspective-select"
          value={perspective}
          onChange={(e) => onPerspectiveChange(Number(e.target.value) as 0 | 1)}
        >
          <option value={0}>{p0Name}</option>
          <option value={1}>{p1Name}</option>
        </select>
      </label>
    </div>
  );
}
