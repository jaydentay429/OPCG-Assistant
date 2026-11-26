import type { Metadata } from "next";
import { buildPageMetadata } from "@/lib/seo";
import { UnsubscribeClient } from "./UnsubscribeClient";

export const metadata: Metadata = buildPageMetadata({
  title: "取消郵件提醒",
  description: "取消 OPCG 卡牌助手的新卡與價格變動郵件提醒。",
  path: "/alerts/unsubscribe",
  noIndex: true,
});

export default function UnsubscribePage() {
  return (
    <main className="container stack" style={{ maxWidth: 560, paddingTop: "2rem" }}>
      <UnsubscribeClient />
    </main>
  );
}
