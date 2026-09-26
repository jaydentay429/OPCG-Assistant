import Link from "next/link";
import { cardNotFoundMetadata } from "@/lib/cardNotFoundMetadata";

export const metadata = cardNotFoundMetadata;

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
