#!/bin/bash

# Test script for send_notification function in main.sh
# Usage: ./test_notification.sh [--mock]
#   --mock: Simulates curl success without sending actual network requests.

set -u

# Change to the directory of this script
cd "$(dirname "$0")"

MAIN_SCRIPT="../main.sh"
REAL_ENV="../.env"
TEMP_ENV=".env"
MOCK_CURL=false

# Parse arguments
for arg in "$@"; do
  case $arg in
    --mock)
      MOCK_CURL=true
    ;;
    --help)
      echo "Usage: $0 [--mock]"
      echo "  --mock  Mock curl command to simulate success without sending network requests."
      exit 0
    ;;
  esac
done

if [ ! -f "$MAIN_SCRIPT" ]; then
  echo "❌ Error: main.sh not found at $MAIN_SCRIPT"
  exit 1
fi

# Create a temporary log file
LOG_FILE=$(mktemp)
echo "INFO: Initializing test log file at $LOG_FILE" > "$LOG_FILE"
echo "INFO: Previous log entry 1" >> "$LOG_FILE"
echo "INFO: Previous log entry 2" >> "$LOG_FILE"

# Mock log_msg to output to stdout
log_msg() {
  local level=$1
  shift
  echo -e "📝 [LOG $level] $*"
}

# Mock curl if requested
if [ "$MOCK_CURL" = true ]; then
  curl() {
    echo "🔗 [MOCK CURL] Would execute: curl $*"
    return 0
  }
fi

# Helper to extract function body from main.sh
extract_function() {
  local func_name=$1
  local file=$2
  sed -n "/^$func_name() {/,/^}/p" "$file"
}

echo "🔍 Extracting functions from main.sh..."
# Source the extracted functions
eval "$(extract_function get_env_var "$MAIN_SCRIPT")"
eval "$(extract_function send_notification "$MAIN_SCRIPT")"

# Verify extraction
if ! command -v send_notification >/dev/null; then
  echo "❌ Error: Could not extract send_notification function."
  rm "$LOG_FILE"
  exit 1
fi

# Setup .env
CLEANUP_ENV=false
if [ -f "$REAL_ENV" ]; then
  echo "📂 Found existing .env, using it."
  cp "$REAL_ENV" "$TEMP_ENV"
  CLEANUP_ENV=true
else
  echo "⚠️ No .env found in project root. Creating dummy .env."
  echo "TG_TOKEN=123456:ABC-DummyToken" > "$TEMP_ENV"
  echo "TG_CHATID=12345678" >> "$TEMP_ENV"
  CLEANUP_ENV=true
fi

# Trap cleanup
cleanup() {
  rm -f "$LOG_FILE"
  if [ "$CLEANUP_ENV" = true ]; then
    rm -f "$TEMP_ENV"
  fi
}
trap cleanup EXIT

# Run the test
echo "🚀 Sending test notification..."
send_notification "Test message from test_notification.sh at $(date)"

if [ $? -eq 0 ]; then
  echo "✅ Notification sent successfully (or mocked)."
else
  echo "❌ Failed to send notification."
  exit 1
fi