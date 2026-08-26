import type { Metadata } from "next";
import { LegalDoc } from "@/components/LegalDoc";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "Disclaimer | OPCG Card Assistant",
  description: "Unofficial fan-tool disclaimer for OPCG Card Assistant.",
  path: "/legal/disclaimer",
  absoluteTitle: true,
});

export default function DisclaimerPage() {
  return <LegalDoc doc="disclaimer" />;
}
