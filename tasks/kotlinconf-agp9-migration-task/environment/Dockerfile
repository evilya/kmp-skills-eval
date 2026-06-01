FROM --platform=linux/amd64 ubuntu:24.04

# ── Build-time version pins ────────────────────────────────────────────────────
ARG JAVA_VERSION_DEFAULT=17.0.11-tem
ARG JAVA_VERSION_EXTRA=21.0.3-tem
ARG GRADLE_VERSION=9.1.0
ARG ANDROID_API=35
ARG ANDROID_BUILD_TOOLS=35.0.0
ARG ANDROID_CMDLINE_TOOLS_ZIP=commandlinetools-linux-11076708_latest.zip
ARG DEBIAN_FRONTEND=noninteractive

# ── Environment ────────────────────────────────────────────────────────────────
ENV GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
ENV JAVA_HOME="/root/.sdkman/candidates/java/current"
ENV PATH="/root/.sdkman/candidates/java/current/bin:/root/.sdkman/candidates/gradle/current/bin:${PATH}"
ENV ANDROID_SDK_ROOT="/opt/android-sdk"
ENV ANDROID_HOME="/opt/android-sdk"
ENV PATH="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:${PATH}"
ENV GRADLE_OPTS="-Dorg.gradle.vfs.watch=false"

# ── System dependencies ────────────────────────────────────────────────────────
RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        software-properties-common curl zip unzip \
        build-essential git python3 python3-pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── SDKMAN + JDK / Gradle / Kotlin ────────────────────────────────────────────
COPY scripts/install-sdkman-tools.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/install-sdkman-tools.sh && \
    /usr/local/bin/install-sdkman-tools.sh \
        "$JAVA_VERSION_DEFAULT" "$JAVA_VERSION_EXTRA" \
        "$GRADLE_VERSION"

# ── Android SDK ────────────────────────────────────────────────────────────────
COPY scripts/install-android-sdk.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/install-android-sdk.sh && \
    /usr/local/bin/install-android-sdk.sh \
        "$ANDROID_SDK_ROOT" "$ANDROID_CMDLINE_TOOLS_ZIP" \
        "$ANDROID_API" "$ANDROID_BUILD_TOOLS"

# ── Gradle global properties ───────────────────────────────────────────────────
RUN mkdir -p /root/.gradle && \
    echo "kotlin.native.ignoreDisabledTargets=true" >> /root/.gradle/gradle.properties

# ── Clone repo and warm caches at build time ───────────────────────────────────
WORKDIR /root/agent-work
RUN git init . && \
    git remote add origin https://github.com/JetBrains/kotlinconf-app.git && \
    git fetch --depth 1 origin 4c5b079cc4df8205ab390036f45987e13ebac32c && \
    git checkout --detach FETCH_HEAD

# Warm Gradle / plugin caches without running checks (some repos have pre-existing
# format/lint violations at the base commit). `|| true` keeps the image build green.
RUN bash -c "source /root/.sdkman/bin/sdkman-init.sh && \
    ./gradlew help && \
    ./gradlew assemble -x lint -x check -x test -x spotlessCheck -x spotlessKotlinCheck --continue || true"

RUN mkdir -p /logs
