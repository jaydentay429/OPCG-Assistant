import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/community/admin",
          "/community/me",
          "/community/new",
          "/reset-password",
          "/play/history",
          "/play/spectate",
          "/binder/s/",
          "/api/",
        ],
      },
    ],
    sitemap: new URL("/sitemap.xml", `${SITE_URL}/`).toString(),
    host: SITE_URL,
  };
}
