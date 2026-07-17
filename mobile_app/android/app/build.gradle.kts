plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.mobile_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.mobile_app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        ndk {
            abiFilters.clear()
            abiFilters.add("arm64-v8a")
        }
    }
    packaging {
        resources {
            excludes.add("**/desktop.ini")
        }
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

// Workaround for persistent Windows CMake metadata file locks during APK build.
// This app relies on prebuilt plugin binaries and does not need app-level CMake tasks.
tasks.configureEach {
    if (name.startsWith("configureCMake") || name.startsWith("buildCMake")) {
        enabled = false
    }
    if (name.startsWith("cleanMerge") && name.endsWith("Assets")) {
        enabled = false
    }
}

tasks.matching { name == "mergeDebugResources" || name == "mergeReleaseResources" }.configureEach {
    doFirst {
        repeat(5) {
            delete(fileTree(layout.buildDirectory) { include("**/desktop.ini") })
            delete(fileTree(file("build")) { include("**/desktop.ini") })
            delete(fileTree("build/generated/res/processDebugGoogleServices") { include("**/desktop.ini") })
            delete(fileTree("build/generated/res/processReleaseGoogleServices") { include("**/desktop.ini") })
            Thread.sleep(200)
        }
    }
}

tasks.register("deleteDesktopIni") {
    doLast {
        delete(fileTree(layout.buildDirectory) { include("**/desktop.ini") })
        delete(fileTree(file("build")) { include("**/desktop.ini") })
        delete(fileTree(file("src/main/res")) { include("**/desktop.ini") })
        if (org.gradle.internal.os.OperatingSystem.current().isWindows) {
            exec {
                commandLine(
                    "cmd",
                    "/c",
                    "attrib",
                    "-s",
                    "-h",
                    "/s",
                    "/d",
                    "build\\generated\\res\\processDebugGoogleServices"
                )
                isIgnoreExitValue = true
            }
            exec {
                commandLine(
                    "cmd",
                    "/c",
                    "attrib",
                    "-s",
                    "-h",
                    "/s",
                    "/d",
                    "build\\generated\\res\\processReleaseGoogleServices"
                )
                isIgnoreExitValue = true
            }
        }
    }
}

tasks.matching { name.startsWith("process") && name.endsWith("GoogleServices") }.configureEach {
    doFirst {
        delete(fileTree(layout.buildDirectory) { include("**/desktop.ini") })
        delete(fileTree(file("build")) { include("**/desktop.ini") })
        delete(fileTree(file("src/main/res")) { include("**/desktop.ini") })
    }
    finalizedBy("deleteDesktopIni")
}

tasks.matching { name == "mergeDebugResources" || name == "mergeReleaseResources" }.configureEach {
    dependsOn("deleteDesktopIni")
}
