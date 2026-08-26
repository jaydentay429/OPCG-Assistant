import type { Metadata } from "next";
import { Suspense } from "react";
import { ResetPasswordClient } from "@/components/ResetPasswordClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "重設密碼 | OPCG 卡牌助手",
  description: "重設 OPCG 卡牌助手帳號密碼。",
  path: "/reset-password",
  absoluteTitle: true,
  noIndex: true,
});

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <ResetPasswordClient />
    </Suspense>
  );
}
