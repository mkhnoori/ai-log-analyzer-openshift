#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ollama-host-config.sh
#  Configures Ollama to listen on 0.0.0.0 (all interfaces) so that the
#  OpenShift pod can reach it via host.crc.testing:11434
#  Run this ONCE on your Mac before deploying to OpenShift.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "Configuring Ollama to listen on all interfaces..."

# Stop the current Ollama service
brew services stop ollama 2>/dev/null || true
sleep 2

# Create a launchd plist that sets OLLAMA_HOST=0.0.0.0
PLIST=~/Library/LaunchAgents/com.ollama.ollama.plist

# Back up the original if it exists
if [[ -f "$PLIST" ]]; then
  cp "$PLIST" "${PLIST}.backup"
  echo "  Backed up original plist to ${PLIST}.backup"
fi

# Write updated plist with OLLAMA_HOST env var
cat > "$PLIST" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ollama.ollama</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/ollama</string>
    <string>serve</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key>
    <string>0.0.0.0</string>
    <key>HOME</key>
    <string>/Users/REPLACE_WITH_YOUR_USERNAME</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/ollama.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/ollama.err.log</string>
</dict>
</plist>
EOF

# Replace placeholder with actual username
sed -i '' "s/REPLACE_WITH_YOUR_USERNAME/$(whoami)/g" "$PLIST"

# Reload and start
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

sleep 3

# Verify
if curl -s --connect-timeout 5 http://0.0.0.0:11434 > /dev/null 2>&1; then
  echo "  ✓ Ollama is now listening on 0.0.0.0:11434"
else
  echo "  Checking on localhost..."
  if curl -s --connect-timeout 5 http://localhost:11434 > /dev/null 2>&1; then
    echo "  ✓ Ollama is running on localhost:11434"
  else
    echo "  ⚠ Ollama may still be starting. Wait 10s and check:"
    echo "    curl http://localhost:11434"
  fi
fi

echo ""
echo "Ollama host configuration complete."
echo "Models available:"
ollama list
echo ""
echo "From inside OpenShift pods, Ollama is reachable at:"
echo "  http://host.crc.testing:11434"
