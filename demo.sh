#!/usr/bin/env bash
# End-to-end demo. Requires ANTHROPIC_API_KEY and internet access.
#
# Usage: ./demo.sh
#
# Make sure the package is installed (pip install -e .) and the venv is active,
# or prefix commands with `.venv/bin/python -m agent ...`.

set -euo pipefail

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set}"

AGENT="${AGENT_BIN:-python -m agent}"
HR="================================================================"

print_step() {
    echo
    echo "$HR"
    echo "== $1"
    echo "$HR"
}

print_step "1. Clear memory/"
rm -rf memory/
mkdir -p memory/

print_step "2. Ensure contradiction fixture exists"
if [[ ! -f fixtures/linear_contradiction.pdf ]]; then
    python fixtures/make_contradiction_pdf.py
fi
ls -l fixtures/linear_contradiction.pdf

print_step "3. Ingest https://linear.app"
$AGENT ingest-url https://linear.app

print_step "4. inspect — memory tree"
$AGENT inspect

print_step "4b. inspect --domain company_overview"
$AGENT inspect --domain company_overview || true

print_step "4c. inspect --domain pricing"
$AGENT inspect --domain pricing || true

print_step "5. chat — initial questions"
cat > /tmp/agent_demo_script_1.txt <<'EOF'
What does this company do?
How much does it cost?
Who are their customers?
EOF
$AGENT chat --script /tmp/agent_demo_script_1.txt

print_step "6. ingest-file fixtures/linear_contradiction.pdf"
$AGENT ingest-file fixtures/linear_contradiction.pdf

print_step "7. changelog tail — conflict should be visible"
$AGENT inspect --changelog --tail 30

print_step "8. chat — ask about pro plan pricing (expect conflict disclosure)"
cat > /tmp/agent_demo_script_2.txt <<'EOF'
How much does the pro plan cost?
EOF
$AGENT chat --script /tmp/agent_demo_script_2.txt

print_step "9. chat — multi-turn user correction"
cat > /tmp/agent_demo_script_3.txt <<'EOF'
Actually, their enterprise plan is $500/mo.
What is the enterprise plan priced at?
EOF
$AGENT chat --script /tmp/agent_demo_script_3.txt

print_step "10. inspect --working (session history + active_context)"
$AGENT inspect --working

echo
echo "Demo complete."
