#!/bin/bash
# install-sdkman-tools.sh
# Installs SDKMAN and uses it to install JDK, Gradle, and Kotlin.
#
# Usage: install-sdkman-tools.sh <java-default> <java-extra> <gradle> <kotlin>
# Example: install-sdkman-tools.sh 17.0.11-tem 21.0.3-tem 9.1.0 2.2.0
set -ex

JAVA_DEFAULT="${1:?java-default version required}"
JAVA_EXTRA="${2:?java-extra version required}"
GRADLE_VERSION="${3:?gradle version required}"

export SDKMAN_AUTO_ANSWER=true
export SDKMAN_NONINTERACTIVE=true

# ── Install SDKMAN ─────────────────────────────────────────────────────────────
curl -s "https://get.sdkman.io" | bash

# Override SDKMAN's own config to ensure non-interactive mode
# (env vars alone are not enough; SDKMAN reads this file after init)
sed -i 's/sdkman_auto_answer=false/sdkman_auto_answer=true/g' /root/.sdkman/etc/config

# Make SDKMAN available in non-interactive shells
echo 'source "/root/.sdkman/bin/sdkman-init.sh"' >> /root/.bashrc
echo 'source "/root/.sdkman/bin/sdkman-init.sh"' >> /root/.profile

# ── Install SDK candidates ─────────────────────────────────────────────────────
# shellcheck source=/dev/null
source /root/.sdkman/bin/sdkman-init.sh

# JDK 17 is the minimum required by AGP 9; JDK 21 is available for toolchain resolution
sdk install java "$JAVA_DEFAULT"
sdk install java "$JAVA_EXTRA"
sdk default java "$JAVA_DEFAULT"
sdk install gradle "$GRADLE_VERSION"


