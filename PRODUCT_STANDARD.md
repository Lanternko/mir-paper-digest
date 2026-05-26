# MIR Digest Product Standard

Version: 2026-05-26
Owner: local MIR automation `mir`

This file is the source of truth for the daily MIR Digest website. The automation must read this file before generating a report. If this file is missing or the generated HTML violates the mandatory contract below, the automation should fail instead of publishing a lower-quality report.

## 1. Product Promise

The product is not an HTML attachment. It is a small research digest site for daily decision-making.

Each issue must help the reader answer, within 10 seconds:

- What are today's two papers?
- Which one is closest to MeanAudio?
- Which one is broader but important or inspiring?
- Why should I read each paper?
- What is the smallest next experiment or action?

## 2. Content Priority

Always rank topics in this order:

1. MeanAudio / text-to-audio / text-to-music generation.
2. `karaoke-jp`: singing voice, separation, pitch, Japanese lyrics, alignment, MIDI/score, karaoke rendering.
3. General MIR, genre classification, tagging, and representation learning.

Freshness is not enough. Selection must consider quality, relevance, baselines, evaluation reliability, reproducibility signals, and usefulness for the user's experiments.

## 3. Information Architecture

Use date-first, topic-second architecture.

Mandatory now:

- Daily issue page: `reports/YYYY-MM-DD.html`.
- Public index: latest issue plus issue archive.
- Each issue shows exactly two paper cards.

Required product direction:

- Month archive for returning to past issues.
- Topic/tag archive for returning to a research thread.
- Canonical detail page per paper for sharing, SEO, and citation.
- RSS feed once the site has stable public history.

Do not replace canonical pages with modals. The daily page can use disclosure/expand sections for scanning, but long-term reading and sharing should belong to stable detail URLs.

## 4. Paper Card Contract

Every daily issue card must include:

- Stable slot number, `01` or `02`.
- Primary track: `MeanAudio`, `karaoke-jp`, or `MIR`.
- Quality/freshness label.
- One primary topic signal and at most 2-3 visible secondary tags.
- Full paper title.
- Short TLDR: one sentence, ideally 55-110 Traditional Chinese characters or a compact English fallback from the source.
- Source link button.
- Expand control for the long summary.

The card must not rely on color alone to communicate meaning.

## 5. Long Summary Contract

Expanded content must use a fixed structure so the reader learns where to look:

- Problem: what question or bottleneck the paper addresses.
- Method: what technique or system is proposed.
- Data: datasets, benchmarks, examples, or what to verify if unclear.
- Findings: the reported result or why it may matter.
- Limitations: what could be weak, missing, or misleading.
- Editor note: how it connects to MeanAudio, karaoke-jp, or the next smallest experiment.

Never paste a full abstract as the final product. Abstracts can be used as source material, but the site should provide original digest writing or clearly compacted notes.

## 6. Interaction And Accessibility

Disclosure must be keyboard-accessible and screen-reader-friendly.

Mandatory:

- Use a real `button` or native `<summary>`.
- Maintain `aria-expanded` and `aria-controls` when using custom buttons.
- Provide visible focus styles.
- Ensure mobile width does not overflow at 390 px.
- Respect `prefers-reduced-motion` if animations are added.
- Print/PDF output should reveal long-summary content.

## 7. Visual Direction

Reading comes first, scanning second, decoration last.

Use:

- Calm light background.
- Strong readable text.
- 1 px borders or very subtle shadows.
- Single-column mobile layout.
- Clear spacing rhythm.

Avoid:

- Copying another site's colors, logos, illustrations, wording, or trade dress.
- Decorative gradients, glass effects, or hero-heavy marketing layout.
- Dense dashboard controls for a two-paper issue.
- Text overflow, clipped buttons, and hidden horizontal scroll on mobile.

## 8. Legal And Source Hygiene

Learn patterns, not skin.

Allowed:

- Date archives.
- Tag chips.
- Reading time / issue labels.
- Disclosure/accordion behavior.
- Short digest cards.

Not allowed:

- Copying another site's brand, logo, favicon, layout details, illustrations, or distinctive wording.
- Republishing full abstracts as if they were original writing.
- Hotlinking or copying paper figures without permission.
- Publishing Discord webhooks, tokens, local secrets, or local-only paths.

## 9. Automation QA Gate

Before publishing, the automation must verify:

- This product standard file exists and can be read.
- Generated report contains no Discord webhook URL.
- Generated report contains no local `D:\...` path.
- Generated report contains exactly two `.paper-card` entries.
- Each card has a source link and an expand control.
- The page includes reading order, tags, quality/freshness, short TLDR, and long-summary sections.
- Long-summary labels include Problem, Method, Data, Findings, Limitations, and Editor note (or Traditional Chinese equivalents).
- Mobile layout has been designed for 390 px width; template CSS must not force a wider main layout.

If a check fails, do not publish. Fix the template or content first.

## 10. Manual Review Checklist

Before a redesign is considered done:

- Open the page on desktop and mobile width.
- Expand at least one card.
- Confirm the page is useful before expanding.
- Confirm the expanded content is useful after expanding.
- Confirm issue index still points to the latest page.
- Confirm no secrets appear in HTML, PDF, repo files, Discord messages, or memory files.

