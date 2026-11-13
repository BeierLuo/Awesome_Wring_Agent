# Caret 0.3.4

Download [Caret.dmg](Caret.dmg?raw=true). Verify the download with `shasum -a 256 Caret.dmg` against [SHA256SUMS](SHA256SUMS).

This build targets Apple Silicon macOS. The DMG includes the application and UI, but requires the separately provisioned Python runtime and LaTeX tools described in the root README. It is not a standalone installer for a fresh machine. The app is locally ad-hoc signed, not Developer ID notarized.

Changes and validation are listed in [CHANGELOG.md](../../CHANGELOG.md).

The artifact contains application code, generic bundled instructions and icons. It excludes workspaces, manuscripts, conversations, personal preferences, API settings, credentials and the external runtime. File/content scans were performed before upload; existing repository history is unchanged.
