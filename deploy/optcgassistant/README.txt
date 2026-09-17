optcgassistant.com — Ubuntu 24.04 部署备忘
========================================

DNS（你已配置，核对即可）
  A  @     → 165.245.180.246
  A  www   → 165.245.180.246
  A  api   → 165.245.180.246

代码目录（推荐，无空格）
  /opt/opcg/app
  = 本仓库根目录内的全部内容（含 app.py、frontend/、deploy/、cards/、meta/ 等）。

一次性准备（在 VPS 上）
  若仅用 root： mkdir -p /opt/opcg/app
  若用 ubuntu：  sudo mkdir -p /opt/opcg && sudo chown ubuntu:ubuntu /opt/opcg
  # 用 git clone + 拷贝，或 scp/rsync 把整个仓库同步到 /opt/opcg/app

  cd /opt/opcg/app
  bash deploy/optcgassistant/SETUP.sh

前端构建（Next.js）
  cd /opt/opcg/app/frontend
  # 需要 Node 20+
  # 务必显式设置生产 API（勿用 .env.local 里的 127.0.0.1，否则线上 Failed to fetch）
  NEXT_PUBLIC_API_BASE_URL=https://api.optcgassistant.com npm ci
  NEXT_PUBLIC_API_BASE_URL=https://api.optcgassistant.com \
  NEXT_PUBLIC_PACKS_CDN_URL=https://img.optcgassistant.com npm run build
  # 本机打生产包同样要带上一行；验收：产物里应有 api.optcgassistant.com 作为主 API_BASE
  # standalone 产物供 opcg-web.service 使用
  sudo cp deploy/optcgassistant/opcg-web.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now opcg-web

HTTPS 与反代
  SETUP 会把 deploy/optcgassistant/Caddyfile 装到 /etc/caddy/Caddyfile
  - https://optcgassistant.com 与 https://www.optcgassistant.com → Next.js :3000
  - https://api.optcgassistant.com → FastAPI :8000

切流说明
  1. 本项目已完全切至 Next.js + FastAPI。
  2. 验收四页 + 登录 + 拍照识卡后，保持 opcg-web 指向 :3000。

环境变量
  首次运行会从 env.production.example 复制 .env；请检查并与线上域名一致。
  若 pip 缺依赖，在 /opt/opcg/app/.venv 里补装（可与本机 pip freeze 对照）。

常用命令
  sudo systemctl status opcg-api opcg-web caddy
  sudo journalctl -u opcg-api -f
  sudo journalctl -u opcg-web -f

日常更新（在 Mac 本机）
  # 1) 本地构建前端
  cd frontend
  NEXT_PUBLIC_API_BASE_URL=https://api.optcgassistant.com \
  NEXT_PUBLIC_PACKS_CDN_URL=https://img.optcgassistant.com npm run build
  mkdir -p .next/standalone/.next
  rm -rf .next/standalone/.next/static .next/standalone/public
  cp -R .next/static .next/standalone/.next/static
  cp -R public .next/standalone/public

  # 2) 同步代码（务必排除 .env、用户数据、以及 VPS 正在写的市价）
  #    图片：浏览器优先 img.optcgassistant.com（CDN）；API /packs/ 作 fallback。
  #    卡图文件在 VPS /opt/opcg/app/packs/ + R2；缺图在 VPS 跑 sync_card_images。
  rsync -avz --delete \
    --exclude '.venv' --exclude '__pycache__/' --exclude '.git' --exclude '.DS_Store' \
    --exclude '.env' --exclude 'packs/' --exclude 'preview/images/' --exclude 'rclone*' \
    --exclude 'frontend/node_modules/' --exclude 'frontend/.next/' \
    --exclude 'meta/auth.db' --exclude 'meta/rank.db' --exclude 'meta/forum.db' --exclude 'meta/topdecks_likes.db' --exclude 'meta/card_comments.db' --exclude 'meta/user_*.json' \
    --exclude 'meta/analytics.db' --exclude 'meta/analytics.db-*' \
    --exclude 'meta/replays/' \
    --exclude 'meta/market_prices.json' --exclude 'meta/yuyu_sync_cursor.json' \
    --exclude 'meta/photo_hash_index.json' --exclude 'meta/photo_clip_index.npz' \
    "/Users/jayden/Documents/OPCG_Project/" \
    root@165.245.180.246:/opt/opcg/app/
  rsync -avz --delete frontend/.next/standalone/ root@165.245.180.246:/opt/opcg/app/frontend/.next/standalone/
  rsync -avz --delete frontend/.next/static/ root@165.245.180.246:/opt/opcg/app/frontend/.next/static/
  rsync -avz --delete frontend/public/ root@165.245.180.246:/opt/opcg/app/frontend/public/

  # 3) 依赖（尤其 OpenCC：缺了会导致简繁特征搜索失效）+ unit + 重启
  #    注意：不要 kill 正在跑的 sync_yuyutei_prices / sync_card_images
  ssh root@165.245.180.246 'cd /opt/opcg/app && .venv/bin/pip install -r requirements.txt && \
    cp deploy/optcgassistant/opcg-api.service /etc/systemd/system/opcg-api.service && \
    systemctl daemon-reload && systemctl restart opcg-api opcg-web'

  # 4) 快速验收
  curl -sS https://api.optcgassistant.com/ | head
  # 期望含 "opencc": true 与 priced_count

比赛卡组（ONE PIECE TOP DECKS）
  # 本机或 VPS 同步 Japan/Asia + English 全部 meta：
  cd /opt/opcg/app   # 或本机仓库根目录
  .venv/bin/python sync_topdecks.py            # 增量：只抓 modified 有变的 meta
  .venv/bin/python sync_topdecks.py --full     # 强制全量重抓
  # 产出：meta/topdecks_decks.json（部署时需 rsync 带上；勿排除）
  # API：GET /topdecks/meta 、/topdecks/decks 、/topdecks/decks/{id}（按 mtime 自动热加载）
  # 每日自动同步（VPS cron，14:00 HKT / 06:00 UTC）：
  bash /opt/opcg/app/deploy/optcgassistant/run_daily_topdecks_sync.sh
  日志：/opt/opcg/logs/daily_topdecks_latest.log
  crontab:（用 bash 调用，避免脚本丢 +x 时 Permission denied）
    0 6 * * * bash /opt/opcg/app/deploy/optcgassistant/run_daily_topdecks_sync.sh >> /opt/opcg/logs/daily_topdecks_cron.log 2>&1
  # 页面注明来源 onepiecetopdecks.com

预览卡（官网 cardlist 尚未上架时，例如 OP17）
  本机：python sync_preview_cards.py --set OP17
  同步代码后在 VPS 再跑同一条（不要 rsync packs/ 或 preview/images/）
  官网 cardlist 有该系列后：
    python sync_official_cards.py --with-images
    python sync_card_images.py --overwrite-preview

每日价格同步（VPS cron，全库家族扫；遇 429 写 checkpoint，下午续跑）
  每个基础号一天搜一次，同页写入该号全部成员。漏价/幽灵价优先，其余按最旧 last_checked。
  不跑 two-pass 异图哈希；官方卡表+卡图拆到另一条 cron。
  bash /opt/opcg/app/deploy/optcgassistant/run_daily_price_sync.sh
  日志：/opt/opcg/logs/daily_price_latest.log
  checkpoint：/opt/opcg/app/meta/yuyu_sync_cursor.json（VPS 本地；rsync 须排除）
  crontab:（用 bash，避免脚本丢 +x）
    0 4 * * * bash /opt/opcg/app/deploy/optcgassistant/run_daily_price_sync.sh >> /opt/opcg/logs/daily_price_cron.log 2>&1
    0 8 * * * bash /opt/opcg/app/deploy/optcgassistant/run_daily_price_sync.sh >> /opt/opcg/logs/daily_price_cron.log 2>&1

每日官方卡表+卡图（VPS cron，10:00 HKT / 02:00 UTC）
  与抓价分开，避免 429 或官网超时把另一半一起杀掉。
  bash /opt/opcg/app/deploy/optcgassistant/run_daily_official_sync.sh
  日志：/opt/opcg/logs/daily_official_latest.log
  crontab:
    0 2 * * * bash /opt/opcg/app/deploy/optcgassistant/run_daily_official_sync.sh >> /opt/opcg/logs/daily_official_cron.log 2>&1

每日流量日报邮件（VPS cron，00:05 HKT / 16:05 UTC）
  统计「昨天」香港时间的浏览量 / 独立访客，发到 ANALYTICS_REPORT_EMAIL。
  bash /opt/opcg/app/deploy/optcgassistant/run_daily_analytics_email.sh
  日志：/opt/opcg/logs/daily_analytics_latest.log
  crontab:
    5 16 * * * /opt/opcg/app/deploy/optcgassistant/run_daily_analytics_email.sh >> /opt/opcg/logs/daily_analytics_cron.log 2>&1
  发信走 Resend HTTPS（.env：RESEND_API_KEY + RESEND_FROM=OPCG Assistant <noreply@optcgassistant.com>）。
  域名 DNS：python3 scripts/configure_resend.py --api-key re_...  把打印的记录加到 Cloudflare（灰云）。
  测试：python3 scripts/configure_resend.py --api-key re_... --test-to you@example.com
  漏发补寄（本机有 Gmail SMTP 时）：
    scp root@165.245.180.246:/opt/opcg/app/meta/analytics.db /tmp/opcg-analytics.db
    cd /opt/opcg/app && ANALYTICS_DB_FILE=/tmp/opcg-analytics.db .venv/bin/python scripts/send_daily_analytics_report.py --day YYYY-MM-DD
  .env 需配置：ANALYTICS_ENABLED=1、ANALYTICS_REPORT_EMAIL、以及
  ANALYTICS_EXCLUDE_VISITOR_IDS / USERNAMES（排除你自己的测试流量）

把线上价格拉回本机
  rsync -avz root@165.245.180.246:/opt/opcg/app/meta/market_prices.json \
    "/Users/jayden/Documents/OPCG_Project/meta/market_prices.json"

卡图 CDN（img.optcgassistant.com）Cloudflare 缓存
  前端 CardImg 优先 img 子域；缺图才回退 api.../packs/ 与 /images/card/。
  若 cf-cache-status 长期为 DYNAMIC，在 Cloudflare → Rules → Cache Rules 新增：
    When: Hostname equals img.optcgassistant.com
    Then: Cache eligibility = Eligible for cache；Edge TTL = 7 days；Browser TTL = 7 days
  R2 公共桶也可在对象 metadata 设 Cache-Control: public, max-age=604800。
  验收：curl -sI https://img.optcgassistant.com/OP14-079.png | grep -i cf-cache
    第二次请求期望 HIT 或 STALE（非 DYNAMIC）。

