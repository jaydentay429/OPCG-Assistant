import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

/**
 * `HTML_LIMITED_BOT_UA_RE.source` in Next 15.5.22. `htmlLimitedBots` replaces
 * this list, so the shipped pattern has to keep it and add `Googlebot`.
 */
const NEXT_15_5_DEFAULT_SOURCE =
  "[\\w-]+-Google|Google-[\\w-]+|Chrome-Lighthouse|Slurp|DuckDuckBot|baiduspider|yandex|sogou|bitlybot|tumblr|vkShare|quora link preview|redditbot|ia_archiver|Bingbot|BingPreview|applebot|facebookexternalhit|facebookcatalog|Twitterbot|LinkedInBot|Slackbot|Discordbot|WhatsApp|SkypeUriPreview|Yeti|googleweblight";

const CHROME =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

function shippedBots(): RegExp {
  const source = fs.readFileSync(path.join(process.cwd(), "next.config.ts"), "utf8");
  const match = source.match(/export const htmlLimitedBots =\n {2}\/([\s\S]*?)\/([a-z]*);/);
  assert.ok(match, "htmlLimitedBots regex missing from next.config.ts");
  return new RegExp(match[1], match[2]);
}

describe("htmlLimitedBots", () => {
  it("replaces Next's default list without dropping it, and adds Googlebot", () => {
    const htmlLimitedBots = shippedBots();
    assert.equal(htmlLimitedBots.flags.includes("i"), true);
    assert.equal(htmlLimitedBots.source, `Googlebot|${NEXT_15_5_DEFAULT_SOURCE}`);
    const defaults = new RegExp(NEXT_15_5_DEFAULT_SOURCE, "i");
    assert.equal(defaults.test(CHROME), false);
    assert.equal(
      defaults.test("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
      false,
    );
  });

  it("matches search and social crawlers, and does not match a normal browser", () => {
    const htmlLimitedBots = shippedBots();
    const bots = [
      "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
      "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.264 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
      "Mozilla/5.0 (compatible; Google-InspectionTool/1.0;)",
      "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
      "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
      "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
      "DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)",
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
      "facebookexternalhit/1.1",
      "Twitterbot/1.0",
      "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
      "LinkedInBot/1.0",
      "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    ];
    for (const ua of bots) {
      assert.equal(htmlLimitedBots.test(ua), true, ua);
    }
    assert.equal(htmlLimitedBots.test(CHROME), false);
  });
});
