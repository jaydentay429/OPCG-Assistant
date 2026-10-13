import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "OPCG 卡牌助手";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "64px 72px",
          background: "linear-gradient(145deg, #0b1220 0%, #15233b 48%, #1d3a5f 100%)",
          color: "#f8fafc",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            fontSize: 28,
            letterSpacing: 2,
            color: "#93c5fd",
            textTransform: "uppercase",
          }}
        >
          ONE PIECE CARD GAME
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ fontSize: 84, fontWeight: 800, lineHeight: 1.05 }}>OPCG 卡牌助手</div>
          <div style={{ fontSize: 34, color: "#cbd5e1", maxWidth: 920, lineHeight: 1.35 }}>
            卡牌搜索 · 卡組構築 · 收藏卡冊 · 市場價格 · 即時對戰
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 26, color: "#94a3b8" }}>
          <span>optcgassistant.com</span>
          <span>Search · Build · Collect · Play</span>
        </div>
      </div>
    ),
    size,
  );
}
