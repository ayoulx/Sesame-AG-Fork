#!/usr/bin/env python3
"""构建配置：默认单 ABI、固定签名、dex legacy 打包。

- ABI：默认只出 arm64-v8a；`-PforkAbis=all` 或 `-PforkAbis=arm64-v8a,x86_64` 覆盖。
- 签名：读 keystore/fork-release.properties（不入库），缺失时回退 debug 签名，保证本地能构建。
- 打包：dex 走 legacy 压缩，APK 更小。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "build"
GRADLE = "app/build.gradle.kts"

IMPORT_ANCHOR = "import java.util.Locale"

ABI_ANCHOR = 'var isCIBuild: Boolean = System.getenv("CI").toBoolean()'
ABI_SNIPPET = """
// [fork:build:abi] 默认 arm64-v8a；-PforkAbis=all 出全 ABI，-PforkAbis=a,b 出指定 ABI
val forkAbiProperty: String =
    providers.gradleProperty("forkAbis").orNull?.trim()?.takeIf { it.isNotEmpty() } ?: "arm64-v8a"
val forkAbis: List<String> =
    if (forkAbiProperty == "all") {
        listOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64")
    } else {
        forkAbiProperty.split(",").map { it.trim() }.filter { it.isNotEmpty() }
    }
val forkUniversalApk: Boolean =
    providers.gradleProperty("forkUniversalApk").orNull?.toBoolean() ?: false
"""

PACKAGING_ANCHOR = """    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }"""

PACKAGING_SNIPPET = """    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
        // [fork:build:dex] dex 走 legacy 压缩打包，APK 体积更小
        dex {
            useLegacyPackaging = true
        }
    }"""

SPLITS_ANCHOR = """            include("armeabi-v7a", "arm64-v8a", "x86", "x86_64")
            isUniversalApk = true"""

SPLITS_SNIPPET = """            // [fork:build:splits] ABI 由 forkAbis 决定，默认单 ABI
            include(*forkAbis.toTypedArray())
            isUniversalApk = forkUniversalApk"""

SIGNING_ANCHOR = """    signingConfigs {
        getByName("debug") {
        }
    }"""

SIGNING_SNIPPET = """    signingConfigs {
        getByName("debug") {
        }
        // [fork:build:signing] 固定签名：keystore/fork-release.properties 存在即启用
        create("forkRelease") {
            val propertiesFile = rootProject.file("keystore/fork-release.properties")
            if (propertiesFile.exists()) {
                val properties = Properties()
                propertiesFile.inputStream().use { properties.load(it) }
                storeFile = rootProject.file(properties.getProperty("storeFile", "keystore/fork-release.p12"))
                storePassword = properties.getProperty("storePassword")
                keyAlias = properties.getProperty("keyAlias")
                keyPassword = properties.getProperty("keyPassword")
            }
        }
    }"""

RELEASE_ANCHOR = """        getByName("release") {
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("debug")"""

RELEASE_SNIPPET = """        getByName("release") {
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // [fork:build:releaseSigning] 有固定密钥就用固定密钥，没有则回退 debug 签名
            signingConfig =
                if (rootProject.file("keystore/fork-release.properties").exists()) {
                    signingConfigs.getByName("forkRelease")
                } else {
                    signingConfigs.getByName("debug")
                }"""

NDK_ANCHOR = """        if (isCIBuild) {
            ndk {
                abiFilters.addAll(listOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64"))
            }
        }"""

NDK_SNIPPET = """        if (isCIBuild) {
            ndk {
                // [fork:build:ndk] 与 splits 保持一致，避免打进了没被 split 的 ABI
                abiFilters.addAll(forkAbis)
            }
        }"""


def apply(patch):
    gradle = patch.edit(GRADLE)
    gradle.insert_after(IMPORT_ANCHOR, "\nimport java.util.Properties // [fork:build:import]", "import")
    gradle.insert_after(ABI_ANCHOR, "\n" + ABI_SNIPPET, "abi")
    gradle.replace(PACKAGING_ANCHOR, PACKAGING_SNIPPET, "dex")
    gradle.replace(SPLITS_ANCHOR, SPLITS_SNIPPET, "splits")
    gradle.replace(SIGNING_ANCHOR, SIGNING_SNIPPET, "signing")
    gradle.replace(RELEASE_ANCHOR, RELEASE_SNIPPET, "releaseSigning")
    gradle.replace(NDK_ANCHOR, NDK_SNIPPET, "ndk")


if __name__ == "__main__":
    run(TAG, apply)
