plugins {
    id("com.android.application")
}

android {
    namespace = "com.poolar.projector"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.poolar.projector"
        minSdk = 21
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("org.java-websocket:Java-WebSocket:1.5.4")
    implementation("com.google.code.gson:gson:2.10.1")
}
