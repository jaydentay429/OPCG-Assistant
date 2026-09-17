"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { cardImageUrl, recognizePhoto } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";
import { useI18n } from "@/lib/i18n";
import type { PhotoRecognizeResponse } from "@/lib/types";

function fileToBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const i = raw.indexOf(",");
      resolve(i >= 0 ? raw.slice(i + 1) : raw);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** Ensure short side ≥1280 before upload (helps OCR on phone photos). */
async function prepareBlobForRecognize(input: Blob): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(input);
    const w = bmp.width;
    const h = bmp.height;
    const shortSide = Math.min(w, h);
    const targetShort = 1280;
    let tw = w;
    let th = h;
    if (shortSide > 0 && shortSide < targetShort) {
      const scale = targetShort / shortSide;
      tw = Math.round(w * scale);
      th = Math.round(h * scale);
    } else if (Math.max(w, h) > 2400) {
      const scale = 2400 / Math.max(w, h);
      tw = Math.round(w * scale);
      th = Math.round(h * scale);
    } else {
      bmp.close();
      return input;
    }
    const canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      bmp.close();
      return input;
    }
    ctx.drawImage(bmp, 0, 0, tw, th);
    bmp.close();
    const out = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.92),
    );
    return out || input;
  } catch {
    return input;
  }
}

function stageHintKey(stage?: string): string {
  switch (stage) {
    case "no_id_ocr":
    case "too_few_hints":
      return "photo.hint_no_id";
    case "series_mismatch":
      return "photo.hint_series";
    case "blurry":
    case "hard_filter_no_match":
      return "photo.hint_blurry";
    case "ocr_card_id":
    case "attr_unique":
    case "visual_clear":
      return "photo.hint_ok";
    default:
      return "photo.blurry";
  }
}

export function PhotoPageClient() {
  const { t } = useI18n();
  const router = useRouter();
  const [mode, setMode] = useState<"upload" | "camera">("upload");
  const [preview, setPreview] = useState<string>("");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PhotoRecognizeResponse | null>(null);
  const [error, setError] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((tr) => tr.stop());
    };
  }, []);

  useEffect(() => {
    async function openRearCamera(): Promise<MediaStream> {
      const tryGet = (constraints: MediaStreamConstraints) =>
        navigator.mediaDevices.getUserMedia(constraints);

      // 1) Prefer exact rear camera (mobile).
      try {
        return await tryGet({
          video: {
            facingMode: { exact: "environment" },
            width: { ideal: 1920 },
            height: { ideal: 1440 },
          },
          audio: false,
        });
      } catch {
        /* continue */
      }

      // 2) Soft preference for rear.
      try {
        return await tryGet({
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1920 },
            height: { ideal: 1440 },
          },
          audio: false,
        });
      } catch {
        /* continue */
      }

      // 3) Enumerate and pick a back/rear device by label or facingMode.
      try {
        // Some browsers need a prior permission grant before labels appear.
        const probe = await tryGet({ video: true, audio: false });
        probe.getTracks().forEach((tr) => tr.stop());
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videos = devices.filter((d) => d.kind === "videoinput");
        const rear = videos.find((d) => {
          const label = (d.label || "").toLowerCase();
          return (
            label.includes("back") ||
            label.includes("rear") ||
            label.includes("environment") ||
            label.includes("后") ||
            label.includes("後")
          );
        });
        if (rear?.deviceId) {
          return await tryGet({
            video: {
              deviceId: { exact: rear.deviceId },
              width: { ideal: 1920 },
              height: { ideal: 1440 },
            },
            audio: false,
          });
        }
        // Prefer the last video input on many phones (often rear).
        if (videos.length > 1 && videos[videos.length - 1]?.deviceId) {
          return await tryGet({
            video: {
              deviceId: { exact: videos[videos.length - 1].deviceId },
              width: { ideal: 1920 },
              height: { ideal: 1440 },
            },
            audio: false,
          });
        }
      } catch {
        /* continue */
      }

      // 4) Absolute fallback.
      return tryGet({ video: true, audio: false });
    }

    async function startCam() {
      if (mode !== "camera") {
        streamRef.current?.getTracks().forEach((tr) => tr.stop());
        streamRef.current = null;
        return;
      }
      setError("");
      try {
        const stream = await openRearCamera();
        streamRef.current?.getTracks().forEach((tr) => tr.stop());
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          // Never mirror — card OCR needs the real orientation.
          videoRef.current.style.transform = "none";
          await videoRef.current.play();
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
    startCam();
  }, [mode]);

  function onFile(file: File | null) {
    if (!file) return;
    setBlob(file);
    setPreview(URL.createObjectURL(file));
    setResult(null);
  }

  async function captureFrame() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    const vw = video.videoWidth || 1280;
    const vh = video.videoHeight || 960;
    canvas.width = vw;
    canvas.height = vh;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    const b = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!b) return;
    setBlob(b);
    setPreview(URL.createObjectURL(b));
    setResult(null);
  }

  async function onRecognize() {
    if (!blob) {
      setError(t("photo.no_image"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const prepared = await prepareBlobForRecognize(blob);
      const b64 = await fileToBase64(prepared);
      const res = await recognizePhoto(b64);
      setResult(res);
      const auto =
        Boolean(res.base_card_id || res.card_id) &&
        (res.message === "ok_ocr" ||
          res.stage === "ocr_card_id" ||
          res.stage === "attr_unique" ||
          res.stage === "visual_clear");
      const id = String(res.base_card_id || res.card_id || "").trim();
      if (auto && id) {
        router.push(`/cards/${encodeURIComponent(id)}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("photo.fail"));
    } finally {
      setBusy(false);
    }
  }

  const candidateRows = (result?.candidates || [])
    .map((c) => ({
      id: String(c.base_card_id || c.card_id || "").trim(),
      distance: c.distance,
    }))
    .filter((c) => c.id);

  const singleId =
    !candidateRows.length && (result?.base_card_id || result?.card_id)
      ? String(result.base_card_id || result.card_id)
      : "";

  const hintKey = result ? stageHintKey(result.stage) : "";

  return (
    <div className="stack">
      <Link href="/search">{t("photo.back")}</Link>
      <h1 className="page-title">{t("photo.title")}</h1>
      <p className="muted photo-guide-text">{t("photo.guide")}</p>
      <div className="row">
        <button type="button" className={mode === "upload" ? undefined : "secondary"} onClick={() => setMode("upload")}>
          {t("photo.mode_upload")}
        </button>
        <button type="button" className={mode === "camera" ? undefined : "secondary"} onClick={() => setMode("camera")}>
          {t("photo.mode_camera")}
        </button>
      </div>
      <div className="photo-box">
        {mode === "upload" ? (
          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(e) => onFile(e.target.files?.[0] || null)}
          />
        ) : (
          <div className="stack">
            <div className="photo-camera-wrap">
              <video ref={videoRef} playsInline muted className="photo-camera-video" />
              <div className="photo-card-guide" aria-hidden="true">
                <div className="photo-card-frame">
                  <span className="photo-card-frame-label">{t("photo.guide_card")}</span>
                  <div className="photo-attr-guide photo-attr-guide-cost">
                    <span className="photo-attr-guide-label">{t("photo.guide_cost")}</span>
                  </div>
                  <div className="photo-attr-guide photo-attr-guide-power">
                    <span className="photo-attr-guide-label">{t("photo.guide_power")}</span>
                  </div>
                  <div className="photo-attr-guide photo-attr-guide-counter">
                    <span className="photo-attr-guide-label">{t("photo.guide_counter")}</span>
                  </div>
                  <div className="photo-attr-guide photo-attr-guide-name">
                    <span className="photo-attr-guide-label">{t("photo.guide_name")}</span>
                  </div>
                </div>
              </div>
            </div>
            <button type="button" className="secondary" onClick={captureFrame}>
              {t("photo.capture")}
            </button>
          </div>
        )}
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="preview" src={preview} alt="preview" style={{ marginTop: 12 }} />
        ) : null}
      </div>
      <button type="button" onClick={onRecognize} disabled={busy}>
        {busy ? t("photo.working") : t("photo.submit")}
      </button>
      {error ? <p style={{ color: "#fca5a5" }}>{error}</p> : null}
      {result && hintKey ? <p className="muted">{t(hintKey)}</p> : null}
      {result?.message && result.stage && result.stage !== "ocr_card_id" ? (
        <p className="muted photo-stage-msg">{result.message}</p>
      ) : null}
      {singleId ? (
        <button
          type="button"
          className="secondary"
          onClick={() => router.push(`/cards/${encodeURIComponent(singleId)}`)}
        >
          {displayCardId(singleId)}
        </button>
      ) : null}
      {candidateRows.length ? (
        <div className="photo-candidates">
          {candidateRows.map((row) => (
            <button
              key={row.id}
              type="button"
              className="photo-candidate"
              onClick={() => router.push(`/cards/${encodeURIComponent(row.id)}`)}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={cardImageUrl(row.id)} alt={displayCardId(row.id)} />
              <span className="photo-candidate-meta">
                <strong>{displayCardId(row.id)}</strong>
                {row.distance != null ? (
                  <span className="muted">
                    {t("photo.confidence")}: {String(row.distance)}
                  </span>
                ) : null}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
