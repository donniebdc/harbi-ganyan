import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("kotlin-android")
    id("com.google.gms.google-services")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release imzalama anahtarı (android/key.properties). Dosya yoksa (ör. anahtarın
// olmadığı bir makine) release yine debug anahtarıyla imzalanır ki build kırılmasın.
val keystoreProperties = Properties()
val keyPropertiesPath = providers.environmentVariable("HG_KEY_PROPERTIES").orNull
val keystorePropertiesFile = if (keyPropertiesPath != null)
    file(keyPropertiesPath)
else
    rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "app.harbiganyan.harbi_ganyan"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "app.harbiganyan.harbi_ganyan"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystorePropertiesFile.exists()) {
            create("release") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                val storePath = keystoreProperties["storeFile"] as String
                storeFile = keystorePropertiesFile.parentFile.resolve(storePath)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Sabit release anahtarı varsa onunla imzala (güncellemede oturum korunur).
            // Anahtar yoksa debug ile imzala (geliştirme kolaylığı).
            if (!keystorePropertiesFile.exists()) {
                throw GradleException("Release signing requires HG_KEY_PROPERTIES or android/key.properties.")
            }
            signingConfig = signingConfigs.getByName("release")
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}
