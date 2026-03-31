# Benchmark Report: agp9-migration

**Model:** claude-sonnet-4-6  
**Date:** 2026-03-30T18:53:28Z  
**Projects evaluated:** 2

## Summary

| Metric                      | With Skill | Without Skill | Delta  |
|-----------------------------|------------|---------------|--------|
| **Deterministic pass rate** | 100%       | 47%           | +53%   |
| **Agentic pass rate**       | 100%       | 62%           | +38%   |
| **Avg time**                | 346s       | 152s          | +194s  |
| **Avg cost**                | $0.62      | $0.34         | $+0.27 |

## Results by Project

| Project        | With (det.) | With (agent) | Without (det.) | Without (agent) | Delta (det.) | Delta (agent) |
|----------------|-------------|--------------|----------------|-----------------|--------------|---------------|
| jetcaster      | 100%        | 100%         | 83%            | 88%             | +17%         | +12%          |
| kotlinconf-app | 100%        | 100%         | 10%            | 38%             | +90%         | +62%          |

## Detailed Results

### jetcaster

**With Skill** — 114s, 6453 tokens, $0.35343075

Deterministic checks (6/6 passed):

| Check                            | Result | Evidence                                                                                                                 |
|----------------------------------|--------|--------------------------------------------------------------------------------------------------------------------------|
| agp-version-9-plus               | PASS   | Matched at gradle/libs.versions.toml:3: androidGradlePlugin = "9.0.1"                                                    |
| gradle-wrapper-9-plus            | PASS   | Matched at gradle/wrapper/gradle-wrapper.properties:17: distributionUrl=https\://services.gradle.org/distributions/gr... |
| no-top-level-android-in-sharedUi | PASS   | Confirmed no match in sharedUi/build.gradle.kts for pattern: ^android\s*\{                                               |
| mobile-no-kotlin-android         | PASS   | Confirmed absent from mobile/build.gradle.kts: kotlin.android                                                            |
| mobile-no-kotlinOptions          | PASS   | Confirmed absent from mobile/build.gradle.kts: kotlinOptions                                                             |
| mobile-has-compilerOptions       | PASS   | Found at mobile/build.gradle.kts:25: compilerOptions {                                                                   |

Agentic evaluation (8/8 passed):

| Criterion                                                                        | Result | Evidence                                                                                                                 |
|----------------------------------------------------------------------------------|--------|--------------------------------------------------------------------------------------------------------------------------|
| The sharedUi module's android config remains inside kotlin { androidLibrary {... | PASS   | sharedUi/build.gradle.kts lines 12-18: androidLibrary { namespace, compileSdk, minSdk, androidResources } is nested i... |
| The mobile module's org.jetbrains.kotlin.android plugin is removed (AGP 9 bui... | PASS   | mobile/build.gradle.kts lines 18-22: plugins block only contains android.application, ksp, and compose.compiler. No o... |
| The mobile module's kotlinOptions {} block is migrated to kotlin { compilerOp... | PASS   | mobile/build.gradle.kts lines 24-29: kotlin { compilerOptions { jvmTarget.set(...); freeCompilerArgs.add(...) } } is ... |
| KSP plugin compatibility with AGP 9 is maintained                                | PASS   | gradle/libs.versions.toml line 34: ksp = "2.2.21-2.0.4" which is a modern KSP version compatible with AGP 9. KSP plug... |
| AGP version in gradle/libs.versions.toml is updated to 9.0.0 or higher           | PASS   | gradle/libs.versions.toml line 3: androidGradlePlugin = "9.0.1"                                                          |
| Gradle wrapper in gradle/wrapper/gradle-wrapper.properties is updated to 9.1.... | PASS   | gradle/wrapper/gradle-wrapper.properties line 17: distributionUrl=https\://services.gradle.org/distributions/gradle-9... |
| No removed gradle properties are present in gradle.properties (android.enable... | PASS   | gradle.properties contains no instances of android.enableLegacyVariantApi, android.r8.integratedResourceShrinking, or... |
| The migration does not break the existing dependency structure between modules   | PASS   | mobile/build.gradle.kts lines 152-157: dependencies on projects.core.data, projects.core.designsystem (twice), projec... |

**Without Skill** — 113s, 5836 tokens, $0.30632325

Deterministic checks (5/6 passed):

| Check                            | Result | Evidence                                                                    |
|----------------------------------|--------|-----------------------------------------------------------------------------|
| agp-version-9-plus               | PASS   | Matched at gradle/libs.versions.toml:3: androidGradlePlugin = "9.0.0"       |
| gradle-wrapper-9-plus            | FAIL   | Pattern not matched in gradle/wrapper/gradle-wrapper.properties: gradle-9\. |
| no-top-level-android-in-sharedUi | PASS   | Confirmed no match in sharedUi/build.gradle.kts for pattern: ^android\s*\{  |
| mobile-no-kotlin-android         | PASS   | Confirmed absent from mobile/build.gradle.kts: kotlin.android               |
| mobile-no-kotlinOptions          | PASS   | Confirmed absent from mobile/build.gradle.kts: kotlinOptions                |
| mobile-has-compilerOptions       | PASS   | Found at mobile/build.gradle.kts:25: compilerOptions {                      |

Agentic evaluation (7/8 passed):

| Criterion                                                                        | Result | Evidence                                                                                                                 |
|----------------------------------------------------------------------------------|--------|--------------------------------------------------------------------------------------------------------------------------|
| The sharedUi module's android config remains inside kotlin { androidLibrary {... | PASS   | sharedUi/build.gradle.kts:12-18 — androidLibrary { namespace, compileSdk, minSdk, androidResources } is nested inside... |
| The mobile module's org.jetbrains.kotlin.android plugin is removed (AGP 9 bui... | PASS   | mobile/build.gradle.kts:18-23 — plugins block only contains alias(libs.plugins.android.application), alias(libs.plugi... |
| The mobile module's kotlinOptions {} block is migrated to kotlin { compilerOp... | PASS   | mobile/build.gradle.kts:24-29 — kotlin { compilerOptions { freeCompilerArgs.add(...); jvmTarget.set(...) } } is prese... |
| KSP plugin compatibility with AGP 9 is maintained                                | PASS   | gradle/libs.versions.toml:34 — ksp = "2.2.21-2.0.4" is a KSP 2.x version aligned with the Kotlin version, which is co... |
| AGP version in gradle/libs.versions.toml is updated to 9.0.0 or higher           | PASS   | gradle/libs.versions.toml:3 — androidGradlePlugin = "9.0.0"                                                              |
| Gradle wrapper in gradle/wrapper/gradle-wrapper.properties is updated to 9.1.... | FAIL   | gradle/wrapper/gradle-wrapper.properties:17 — distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.... |
| No removed gradle properties are present in gradle.properties (android.enable... | PASS   | gradle.properties contains no references to android.enableLegacyVariantApi, android.r8.integratedResourceShrinking, o... |
| The migration does not break the existing dependency structure between modules   | PASS   | mobile/build.gradle.kts:151-156 — All module dependencies are intact: projects.core.data, projects.core.designsystem,... |

---

### kotlinconf-app

**With Skill** — 578s, 17515 tokens, $0.88142745

Deterministic checks (10/10 passed):

| Check                                | Result | Evidence                                                                                                                 |
|--------------------------------------|--------|--------------------------------------------------------------------------------------------------------------------------|
| shared-kmp-library-plugin            | PASS   | Found 'androidKotlinMultiplatformLibrary' at shared/build.gradle.kts:9: alias(libs.plugins.androidKotlinMultiplatform... |
| shared-no-old-android-library        | PASS   | Confirmed absent from shared/build.gradle.kts: libs.plugins.androidLibrary                                               |
| shared-no-top-level-android          | PASS   | Confirmed no match in shared/build.gradle.kts for pattern: ^android\s*\{                                                 |
| ui-components-kmp-library-plugin     | PASS   | Found 'androidKotlinMultiplatformLibrary' at ui-components/build.gradle.kts:7: alias(libs.plugins.androidKotlinMultip... |
| ui-components-no-old-android-library | PASS   | Confirmed absent from ui-components/build.gradle.kts: libs.plugins.androidLibrary                                        |
| core-kmp-library-plugin              | PASS   | Found 'androidKotlinMultiplatformLibrary' at core/build.gradle.kts:8: alias(libs.plugins.androidKotlinMultiplatformLi... |
| core-no-old-android-library          | PASS   | Confirmed absent from core/build.gradle.kts: libs.plugins.androidLibrary                                                 |
| androidApp-no-kotlin-multiplatform   | PASS   | Confirmed absent from androidApp/build.gradle.kts: kotlinMultiplatform                                                   |
| agp-version-9-plus                   | PASS   | Matched at gradle/libs.versions.toml:3: agp = "9.0.1"                                                                    |
| version-catalog-kmp-library-plugin   | PASS   | Found 'com.android.kotlin.multiplatform.library' at gradle/libs.versions.toml:112: androidKotlinMultiplatformLibrary ... |

**Without Skill** — 190s, 9913 tokens, $0.38024340000000006

Deterministic checks (1/10 passed):

| Check                                | Result | Evidence                                                                                |
|--------------------------------------|--------|-----------------------------------------------------------------------------------------|
| shared-kmp-library-plugin            | FAIL   | None of the expected strings found in shared/build.gradle.kts                           |
| shared-no-old-android-library        | FAIL   | Still present at shared/build.gradle.kts:9: alias(libs.plugins.androidLibrary)          |
| shared-no-top-level-android          | FAIL   | Pattern still matches at shared/build.gradle.kts:146: android {                         |
| ui-components-kmp-library-plugin     | FAIL   | None of the expected strings found in ui-components/build.gradle.kts                    |
| ui-components-no-old-android-library | FAIL   | Still present at ui-components/build.gradle.kts:7: alias(libs.plugins.androidLibrary)   |
| core-kmp-library-plugin              | FAIL   | None of the expected strings found in core/build.gradle.kts                             |
| core-no-old-android-library          | FAIL   | Still present at core/build.gradle.kts:8: alias(libs.plugins.androidLibrary)            |
| androidApp-no-kotlin-multiplatform   | FAIL   | Still present at androidApp/build.gradle.kts:2: alias(libs.plugins.kotlinMultiplatform) |
| agp-version-9-plus                   | PASS   | Matched at gradle/libs.versions.toml:3: agp = "9.0.0"                                   |
| version-catalog-kmp-library-plugin   | FAIL   | None of the expected strings found in gradle/libs.versions.toml                         |

Agentic evaluation (3/8 passed):

| Criterion                                                                        | Result | Evidence                                                                                                                 |
|----------------------------------------------------------------------------------|--------|--------------------------------------------------------------------------------------------------------------------------|
| All three KMP library modules (shared, ui-components, core) have com.android.... | FAIL   | shared/build.gradle.kts:9, ui-components/build.gradle.kts:7, core/build.gradle.kts:8 all still use `alias(libs.plugin... |
| The android {} blocks in shared, ui-components, and core are nested inside ko... | FAIL   | shared/build.gradle.kts:146, ui-components/build.gradle.kts:78, core/build.gradle.kts:41 — all three modules have the... |
| The androidApp module no longer applies kotlin.multiplatform — it uses only c... | FAIL   | androidApp/build.gradle.kts:2 still applies `alias(libs.plugins.kotlinMultiplatform)`. The kotlinMultiplatform plugin... |
| The androidApp module's sources are moved from androidMain to main (or the so... | FAIL   | androidApp/build.gradle.kts:13 still uses `androidMain.dependencies { ... }` inside a kotlin { sourceSets { } } block... |
| The version catalog has a plugin alias for com.android.kotlin.multiplatform.l... | FAIL   | gradle/libs.versions.toml [plugins] section (lines 109-121) contains no entry for `com.android.kotlin.multiplatform.l... |
| AGP version in gradle/libs.versions.toml is updated to 9.0.0 or higher           | PASS   | gradle/libs.versions.toml:3 — `agp = "9.0.0"` is present, which satisfies the 9.0.0 or higher requirement.               |
| Compose Multiplatform integration still works with the new plugin configuration  | PASS   | shared/build.gradle.kts:10-12 and ui-components/build.gradle.kts:8-9 still apply composeMultiplatform and composeComp... |
| The migration does not break the dependency structure between modules (androi... | PASS   | androidApp/build.gradle.kts:14 — `implementation(projects.shared)`. shared/build.gradle.kts:68-69 — `api(projects.cor... |

---

*Generated by skills-eval on 2026-03-30T18:53:28Z*
