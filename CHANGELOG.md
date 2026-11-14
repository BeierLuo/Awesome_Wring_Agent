# Caret changelog

## 2026-11-14 — Documentation

The main README, agent guide and GitHub release notes are available in English. The main README links to the Chinese edition. This update only changes documentation.

## 0.3.4 — 2026-11-13

- Confirm a chapter type, including Motivation, independently of generating or adopting a writing plan.
- Preserve the choice per chapter and use it for subsequent chat reference lookups.
- Show save failures and disabled-strategy status; preserve manuscript text and other writing settings.
- Include English labels and documented access steps.

Validation: section-type UI and HTTP regressions, next-chat context, existing style-memory and main UI checks, and macOS installation checks.

## 0.3.3 — 2026-11-13

- Use a white workspace with a subtle gray sidebar.
- Resize the sidebar by dragging its edge, restore its width on restart, and reset it by double-clicking.
- Remove transient paragraph-selection messages and display PDF errors without resizing the preview.
- Reuse highlight layers when a paragraph is selected, keep selection colors consistent, and avoid redundant redraws.
- Maintain a per-change development log and archive redundant release bundles after validation.

Validation: workspace interaction regression checks and macOS installation checks, including signature, isolated backend startup and PDF compilation. Real-world paragraph-selection smoothness remains subject to user feedback.

## 0.3.2 — 2026-11-13

- Rename the application to Caret and adopt the new icon set.
- Preserve existing application data compatibility.
- Correct selector hover styling with visible background and shadow transitions.

## 0.3.1 — 2026-11-13

- Merge PDF selection highlights by line to prevent overlapping character shading.
- Compact the composer and model controls.
- Support Enter to send and Shift+Enter for newlines, with input-method composition guards.
