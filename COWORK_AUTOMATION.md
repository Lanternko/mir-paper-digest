# Cowork 每日 MIR Digest 自動化

Version: 2026-07-05

取代舊的本機 Task Scheduler + `run_daily.py` 單體流程。分工如下:

## 架構

```
Cowork 排程任務 (每天 09:00, Asia/Taipei)
  1. clone https://github.com/lanternko/mir-paper-digest (取得 data/papers.csv 去重紀錄)
  2. 搜尋 arXiv (web_fetch: arxiv.org/search, arxiv.org/abs) 與 GitHub (web_fetch: api.github.com/search)
  3. 依主線篩選: (a) MeanAudio / text-to-audio/music 生成 (b) karaoke-jp / 歌詞辨識 / JPOP (c) 泛 MIR
  4. 去重: title / source_url / arXiv ID / DOI 任一命中 data/papers.csv 即跳過
  5. 撰寫繁中摘要 (TLDR + Insight + Try next + Problem/Method/Data/Findings/Limitations/Editor note)
  6. 產出 digests/YYYY-MM-DD.json
  7. 在 clone 內執行: python3 scripts/build_daily.py digests/YYYY-MM-DD.json
     (渲染 reports/*.html + QA gate + 追加 data/papers.csv + 重建 index.html; 失敗即中止, 不 push)
  8. git push (PAT 從 C:\Users\柯子捷\.codex\automations\mir\secrets\github_token.txt 讀取, 絕不寫入 repo 或輸出)

GitHub Actions (.github/workflows/daily-digest.yml)
  push 觸發 (paths: digests/**) → scripts/notify_discord.py 讀取 digest JSON 的
  discord_messages, 逐則 POST 到 repo secret MIR_DISCORD_WEBHOOK
```

## digest JSON schema

見 `scripts/build_daily.py` docstring 與 `load_digest()`。重點:

- `date`: YYYY-MM-DD
- `papers`: 恰好 2 筆, 每筆含 slot/track/title/authors/updated/source_url/tags/quality/
  tldr/insight/try_next/problem/method/data/findings/limitations/editor_note/relevance
- `repo`: 選填, 含 full_name/url/description_zh/why (+ stars/updated/tags)
- `discord_messages`: 1-5 則, 每則 <= 1990 字元, 不得含 webhook URL

## 秘密管理

- Discord webhook: 只存在 GitHub repo secret `MIR_DISCORD_WEBHOOK`。不寫入任何檔案、CSV、HTML、訊息。
- GitHub PAT: 只存在本機 `C:\Users\柯子捷\.codex\automations\mir\secrets\github_token.txt`
  (fine-grained, 僅 lanternko/mir-paper-digest, Contents: Read/Write)。不寫入 repo。

## 失敗行為

- 搜尋不到足夠未重複論文 → 回報並停止, 不 push、不發 Discord。
- QA gate 失敗 → 不 push、不發 Discord (data/papers.csv 也不會進 repo)。
- push 成功但 Action 失敗 → 網站已更新但 Discord 未送達; 排程任務會檢查 Action 結果並回報。

## 與舊系統的差異

- 摘要由 LLM 針對每篇論文實際撰寫, 取代舊 run_daily.py 的關鍵詞啟發式罐頭文字。
- 去重紀錄以 repo 內 data/papers.csv 為準 (公開內容, 無本機路徑、無秘密);
  舊 D:\Projects\mir_paper_log.csv 保留為歷史存檔, 不再更新。
- HTML 渲染 / QA / index 收斂到 scripts/build_daily.py (~700 行, 純標準庫, 無網路)。
- PDF 附件暫停產出 (Discord 改附網站連結)。
