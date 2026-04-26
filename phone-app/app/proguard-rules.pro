# Gson uses reflection for serialization
-keep class com.poolar.controller.model.** { *; }
-keep class com.poolar.controller.network.ApiClient$* { *; }
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}

# WebSocket client
-keep class org.java_websocket.** { *; }
