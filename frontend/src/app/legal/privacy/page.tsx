import type { Metadata } from "next";
import { LegalDoc } from "@/components/LegalDoc";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "Privacy Policy | OPCG Card Assistant",
  description: "Privacy notice for OPCG Card Assistant (optcgassistant.com).",
  path: "/legal/privacy",
  absoluteTitle: true,
});

export default function PrivacyPage() {
  return <LegalDoc doc="privacy" />;
}
