import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "找不到卡牌",
  description: "這個卡號不存在。請回到卡牌搜索查看有效卡牌。",
  robots: {
    index: false,
    follow: false,
    googleBot: {
      index: false,
      follow: false,
    },
  },
};

export default function CardNotFound() {
  return (
    <div className="stack">
      <h1 className="page-title">找不到卡牌</h1>
      <p className="muted">這個卡號不存在，或連結不正確。</p>
      <p className="legal-links">
        <Link href="/search">前往卡牌搜索</Link>
      </p>
    </div>
  );
}
