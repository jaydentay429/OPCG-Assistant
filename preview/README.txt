OP17 等未上 cardlist 的预览卡图
================================

把官方推特 / 商品页存下来的图丢进 images/，文件名必须是卡号：

  preview/images/OP17-001.png
  preview/images/OP17-079-P1.png

然后在「Chinese HK」目录跑：

  python sync_preview_cards.py --set OP17

脚本会：
  1. 拷本地 images/ 到 packs/
  2. 抓日文官网商品页宣传图
  3. 抓 Limitless 已公开的卡资料（费用 / 效果 / 图）
  4. 写入 index/cards_by_id.json（带 "preview": true）

**效果编码（必做，不能只加图/索引）：**
  5. 为每张可玩卡号（含异画）写入 `index/card_effect_overrides.json`
  6. 用 `get_card_entry(card_id)` 确认 ability 未被 normalize 丢掉
  7. 参考 `scripts/README_EFFECTS.md`；复杂卡再跑 fidelity / 对战冒烟
  8. 同步 overrides + index 到 VPS 并 `systemctl restart opcg-api`

不要把 preview/images/ 或 packs/ 整包 rsync 到 VPS。VPS 上再跑同一条命令（或只上传缺的 PNG）。

官网 cardlist 有该系列之后：

  python sync_official_cards.py --with-images
  python sync_card_images.py --overwrite-preview
