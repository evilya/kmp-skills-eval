#!/bin/bash
# install-android-sdk.sh
# Downloads the Android command-line tools and installs the required SDK components.
#
# Usage: install-android-sdk.sh <sdk-root> <cmdline-tools-zip> <api-level> <build-tools-version>
# Example: install-android-sdk.sh /opt/android-sdk commandlinetools-linux-11076708_latest.zip 35 35.0.0
set -euo pipefail

SDK_ROOT="${1:?sdk-root path required}"
CMDLINE_TOOLS_ZIP="${2:?cmdline-tools zip filename required}"
ANDROID_API="${3:?Android API level required}"
BUILD_TOOLS="${4:?build-tools version required}"

CMDLINE_TOOLS_URL="https://dl.google.com/android/repository/${CMDLINE_TOOLS_ZIP}"

# ── Download and unpack command-line tools ─────────────────────────────────────
mkdir -p "$SDK_ROOT/cmdline-tools"
cd "$SDK_ROOT/cmdline-tools"

curl -o sdk.zip "$CMDLINE_TOOLS_URL"
unzip -q sdk.zip -d .
# The zip always extracts to a folder called `cmdline-tools`; rename it to `latest`
# so sdkmanager can find it without a version suffix in PATH.
mv cmdline-tools latest
rm sdk.zip

# ── Accept licenses and install SDK components ─────────────────────────────────
# Accept licenses separately to avoid SIGPIPE from `yes` closing after sdkmanager
# reads all it needs (pipefail would otherwise treat the broken pipe as an error).
yes | "$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK_ROOT" --licenses || true

"$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" \
    --sdk_root="$SDK_ROOT" \
    "platform-tools" \
    "platforms;android-${ANDROID_API}" \
    "build-tools;${BUILD_TOOLS}"