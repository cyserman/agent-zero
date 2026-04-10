#!/usr/bin/env bash
# bootstrap.sh — Full setup for Chris's Agent Zero + NDCoder environment
#
# Run ONCE on Chromebook after cloning the repo:
#   chmod +x bootstrap.sh
#   ./bootstrap.sh
#
# What it does:
#   1. Creates SSD project structure (Legal, skills, memories, etc.)
#   2. Copies templates (truth_spine, punchlist, handoff) into place
#   3. Symlinks knowledge/skills into Agent Zero's usr/ directory
#   4. Sets up Canvas Dropzone
#   5. Verifies Docker + Supabase readiness
#   6. Copies Hermes manager prompt + NDCoder protocol to Shared_Memories

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SSD="/mnt/chromeos/removable/Angie"
VAULT="$SSD/AGENT_VAULT"
PROJECTS="$SSD/Projects"
BACKUPS="$SSD/Backups"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# Agent Zero usr/ directory — adjust if your Docker volume mounts elsewhere
A0_USR="${A0_USR:-$HOME/angie-data2}"

echo "============================================"
echo "  Agent Zero + NDCoder Bootstrap"
echo "============================================"
echo "SSD:      $SSD"
echo "Vault:    $VAULT"
echo "A0 usr:   $A0_USR"
echo "Repo:     $REPO_DIR"
echo ""

# ── Check SSD is mounted ─────────────────────────────────────────────────────
if [[ ! -d "$SSD" ]]; then
    echo "ERROR: SSD not found at $SSD"
    echo "Make sure the external drive is plugged in and shared with Linux."
    echo "(ChromeOS Settings > Files > Share with Linux)"
    exit 1
fi
echo "[1/7] SSD detected."

# ── Create SSD folder structure ───────────────────────────────────────────────
echo "[2/7] Creating SSD folder structure..."

# AGENT_VAULT
mkdir -p "$VAULT/AgentZero_Instances"
mkdir -p "$VAULT/ClaudeCode_Workspaces"
mkdir -p "$VAULT/Shared_Memories"
mkdir -p "$VAULT/Canvas_Dropzone"
mkdir -p "$VAULT/Canvas_Library"

# Projects
mkdir -p "$PROJECTS/Legal/knowledge"
mkdir -p "$PROJECTS/Legal/skills"
mkdir -p "$PROJECTS/Legal/filings"
mkdir -p "$PROJECTS/Legal/evidence/texts"
mkdir -p "$PROJECTS/Legal/evidence/financial"
mkdir -p "$PROJECTS/Legal/evidence/statements"
mkdir -p "$PROJECTS/Legal/notebook_lm_output"
mkdir -p "$PROJECTS/Legal/sources"
mkdir -p "$PROJECTS/CaseCraft"
mkdir -p "$PROJECTS/kidclaw"

# Backups
mkdir -p "$BACKUPS"

echo "  Folder structure created."

# ── Copy templates ────────────────────────────────────────────────────────────
echo "[3/7] Copying templates..."

# Truth spine (only if not already present — don't overwrite user data)
if [[ ! -f "$PROJECTS/Legal/truth_spine.md" ]]; then
    cp "$REPO_DIR/templates/legal/truth_spine.md" "$PROJECTS/Legal/truth_spine.md"
    echo "  + truth_spine.md"
fi

if [[ ! -f "$PROJECTS/Legal/legal_punchlist.md" ]]; then
    cp "$REPO_DIR/templates/legal/legal_punchlist.md" "$PROJECTS/Legal/legal_punchlist.md"
    echo "  + legal_punchlist.md"
fi

# Handoff template to Shared_Memories
cp "$REPO_DIR/templates/handoff.md" "$VAULT/Shared_Memories/handoff_template.md"
echo "  + handoff_template.md"

# Hermes manager prompt
cp "$REPO_DIR/hermes_manager_prompt.md" "$VAULT/Shared_Memories/hermes_manager_prompt.md"
echo "  + hermes_manager_prompt.md"

# NDCoder protocol
cp "$REPO_DIR/docs/ndcoder_protocol.md" "$VAULT/Shared_Memories/ndcoder_protocol.md"
echo "  + ndcoder_protocol.md"

# Phoenix-Nexus skills catalog
cp "$REPO_DIR/docs/phoenix_nexus_skills.md" "$VAULT/Shared_Memories/phoenix_nexus_skills.md"
echo "  + phoenix_nexus_skills.md"

# ── Symlink knowledge + skills into Agent Zero ────────────────────────────────
echo "[4/7] Symlinking into Agent Zero usr/ directory..."

mkdir -p "$A0_USR/knowledge"
mkdir -p "$A0_USR/skills"

# Knowledge
ln -sfn "$PROJECTS/Legal/knowledge" "$A0_USR/knowledge/legal" 2>/dev/null && echo "  -> knowledge/legal" || true
ln -sfn "$VAULT/Shared_Memories" "$A0_USR/knowledge/shared" 2>/dev/null && echo "  -> knowledge/shared" || true

# Skills
ln -sfn "$PROJECTS/Legal/skills" "$A0_USR/skills/legal" 2>/dev/null && echo "  -> skills/legal" || true

# If there's a general skills folder on SSD, link that too
if [[ -d "$SSD/Angee/skills" ]]; then
    ln -sfn "$SSD/Angee/skills" "$A0_USR/skills/angee" 2>/dev/null && echo "  -> skills/angee" || true
fi

# ── Canvas organizer ──────────────────────────────────────────────────────────
echo "[5/7] Setting up Canvas Asset Organizer..."
chmod +x "$REPO_DIR/scripts/canvas_organizer.py" 2>/dev/null || true
echo "  Canvas organizer ready at: scripts/canvas_organizer.py"
echo "  Drop zone: $VAULT/Canvas_Dropzone"
echo "  To run: python3 $REPO_DIR/scripts/canvas_organizer.py &"

# ── Docker check ──────────────────────────────────────────────────────────────
echo "[6/7] Checking Docker..."
if command -v docker &>/dev/null; then
    if docker ps 2>/dev/null | grep -q Angee; then
        echo "  Angee container is RUNNING."
    else
        echo "  Angee container is NOT running."
        echo "  Start it with:"
        echo "    docker run -d --name Angee \\"
        echo "      -p 5080:80 -p 9022:22 -p 9000-9009:9000-9009 \\"
        echo "      -v $A0_USR:/a0/usr:rw \\"
        echo "      agent0ai/agent-zero"
    fi
else
    echo "  Docker not found. Install it or skip if running Agent Zero differently."
fi

# ── Supabase check ────────────────────────────────────────────────────────────
echo "[7/7] Checking Supabase config..."
if [[ -f "$A0_USR/.env" ]]; then
    if grep -q "SUPABASE_URL" "$A0_USR/.env" 2>/dev/null; then
        echo "  Supabase URL found in .env"
    else
        echo "  WARNING: SUPABASE_URL not in .env"
        echo "  Set it in Agent Zero Settings -> External Services -> Supabase Memory"
    fi
    if grep -q "SUPABASE_KEY" "$A0_USR/.env" 2>/dev/null; then
        echo "  Supabase KEY found in .env"
    else
        echo "  WARNING: SUPABASE_KEY not in .env"
    fi
else
    echo "  No .env found at $A0_USR/.env (will be created when Angee starts)"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Bootstrap complete!"
echo "============================================"
echo ""
echo "Your SSD structure:"
echo "  $VAULT/"
echo "    AgentZero_Instances/  ClaudeCode_Workspaces/"
echo "    Shared_Memories/      Canvas_Dropzone/"
echo "  $PROJECTS/"
echo "    Legal/ (truth_spine.md, punchlist, filings, evidence)"
echo "    CaseCraft/  kidclaw/"
echo ""
echo "Next steps:"
echo "  1. Start Angee:  docker start Angee"
echo "  2. Open UI:      http://localhost:5080"
echo "  3. Set Supabase URL + key in Settings -> External Services"
echo "  4. Start Hermes: paste hermes_manager_prompt.md into Gemini 3.1 Pro"
echo "  5. Tell Hermes:  'Priority today is legal filings'"
echo ""
