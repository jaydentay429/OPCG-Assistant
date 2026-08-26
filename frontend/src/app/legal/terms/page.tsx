import type { Metadata } from "next";
import { LegalDoc } from "@/components/LegalDoc";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "Terms of Use | OPCG Card Assistant",
  description: "Terms of use for OPCG Card Assistant (optcgassistant.com).",
  path: "/legal/terms",
  absoluteTitle: true,
});

export default function TermsPage() {
  return <LegalDoc doc="terms" />;
}
