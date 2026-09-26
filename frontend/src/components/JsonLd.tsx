import { jsonLdScript } from "@/lib/seo";

/** Machine-readable JSON-LD. Only pass facts that already appear on the page. */
export function JsonLd({
  data,
}: {
  data: Record<string, unknown> | Array<Record<string, unknown>> | null | undefined;
}) {
  if (!data) return null;
  if (Array.isArray(data) && data.length === 0) return null;
  return (
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(data) }} />
  );
}
