allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

// Put all Gradle outputs outside the repo tree to avoid Windows file locks.
val externalBuildRoot = file("C:/temp/forex_mobile_build")
if (!externalBuildRoot.exists()) {
    externalBuildRoot.mkdirs()
}
rootProject.layout.buildDirectory.value(layout.dir(provider { externalBuildRoot }))

subprojects {
    project.layout.buildDirectory.value(rootProject.layout.buildDirectory.dir(project.name))
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
