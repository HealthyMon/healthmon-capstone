plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.ksp)
    id("androidx.room3") version "3.0.3"
}

android {
    namespace = "com.healthmon.app.mobile"
    compileSdk {
        version = release(36)
    }

    defaultConfig {
        minSdk = 26

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

}

dependencies {
    implementation(libs.play.services.wearable)

    val roomVersion = "3.0.3"
    val sqliteVersion = "2.7.1"

    implementation(libs.androidx.appcompat)
    implementation("androidx.core:core:1.17.0")
    implementation("androidx.core:core-ktx:1.17.0")
    implementation(libs.material)
    implementation("androidx.room3:room3-runtime:${roomVersion}")
    implementation("androidx.sqlite:sqlite-framework:${sqliteVersion}")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.2")
    implementation("androidx.work:work-runtime-ktx:2.11.2")

    ksp("androidx.room3:room3-compiler:$roomVersion")

    testImplementation(libs.junit)
    testImplementation("org.json:json:20250517")
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation("androidx.work:work-testing:2.11.2")
}

room3 { schemaDirectory("$projectDir/schemas") }
