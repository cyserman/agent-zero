#!/usr/bin/env bash
# setup_vault.sh — Move ~/Angee vault to external SSD and symlink into Agent Zero
#
# Usage:
#   chmod +x setup_vault.sh
#   ./setup_vault.sh
#
# Defaults (edit as needed):
#   SOURCE  — where your Angee files currently live
#   VAULT   — destination on the external SSD
#   A0      — Agent Zero's usr/ directory inside Docker or on disk

set -euo pipefail

SOURCE="${SOURCE:-/Angees_docs}"
VAULT="${VAULT:-/mnt/chromeos/removable/angie/AGENT_VAULT}"
A0="${A0:-/home/user/agent-zero/usr}"

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [[ ! -d "$SOURCE" ]]; then
  echo "ERROR: Source directory not found: $SOURCE"
  echo "Set SOURCE= to the correct path and re-run."
  exit 1
fi

# ── Copy vault to SSD ──────────────────────────────────────────────────────────
echo "Copying $SOURCE → $VAULT ..."
mkdir -p "$VAULT"
rsync -avh --progress "$SOURCE/" "$VAULT/"
echo "Done copying."

# ── Create knowledge symlinks ──────────────────────────────────────────────────
echo "Setting up Agent Zero knowledge symlinks..."
mkdir -p "$A0/knowledge"

# Global memories + knowledge
if [[ -d "$VAULT/memories+knowledge_global" ]]; then
  ln -sfn "$VAULT/memories+knowledge_global" "$A0/knowledge/global"
  echo "  → usr/knowledge/global"
fi

# Legal case knowledge
if [[ -d "$VAULT/Legal/knowledge" ]]; then
  ln -sfn "$VAULT/Legal/knowledge" "$A0/knowledge/legal"
  echo "  → usr/knowledge/legal"
fi

# ── Create skills symlinks ─────────────────────────────────────────────────────
echo "Setting up Agent Zero skills symlinks..."
mkdir -p "$A0/skills"

# General Angee skills
if [[ -d "$VAULT/skills" ]]; then
  ln -sfn "$VAULT/skills" "$A0/skills/angee"
  echo "  → usr/skills/angee"
fi

# Legal case skills
if [[ -d "$VAULT/Legal/skills" ]]; then
  ln -sfn "$VAULT/Legal/skills" "$A0/skills/legal"
  echo "  → usr/skills/legal"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "All done! Current links:"
ls -la "$A0/knowledge/" 2>/dev/null || true
ls -la "$A0/skills/"    2>/dev/null || true
echo ""
echo "Next steps:"
echo "  1. Restart Agent Zero (or its Docker container) so it picks up the new dirs."
echo "  2. In Agent Zero Settings → External Services → Supabase Memory,"
echo "     enter your Supabase project URL and API key."
echo "  3. Agent Zero will automatically index your vault docs on first startup."
