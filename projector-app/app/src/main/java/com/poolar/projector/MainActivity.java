package com.poolar.projector;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.Handler;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.TextView;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import java.net.URI;

public class MainActivity extends Activity {
    private ImageView projectionView;
    private TextView statusText;
    private WebSocketClient wsClient;
    private Handler reconnectHandler = new Handler();
    private static final String TAG = "PoolARProjector";
    private static final String DEFAULT_SERVER = "ws://192.168.1.100:8000/api/ws/projector";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        setContentView(R.layout.activity_projection);
        projectionView = findViewById(R.id.projectionView);
        statusText = findViewById(R.id.statusText);
        connectWebSocket();
    }

    private void connectWebSocket() {
        String serverUrl = getSharedPreferences("prefs", MODE_PRIVATE)
            .getString("server_url", DEFAULT_SERVER);
        try {
            wsClient = new WebSocketClient(new URI(serverUrl)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.GONE);
                        Log.d(TAG, "Connected to server");
                    });
                }
                @Override
                public void onMessage(String message) {
                    try {
                        com.google.gson.JsonObject json = new com.google.gson.Gson()
                            .fromJson(message, com.google.gson.JsonObject.class);
                        if ("projection".equals(json.get("type").getAsString())) {
                            String base64 = json.get("image").getAsString();
                            byte[] imgBytes = Base64.decode(base64, Base64.DEFAULT);
                            final Bitmap bitmap = BitmapFactory.decodeByteArray(imgBytes, 0, imgBytes.length);
                            runOnUiThread(() -> projectionView.setImageBitmap(bitmap));
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error decoding image", e);
                    }
                }
                @Override
                public void onClose(int code, String reason, boolean remote) {
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.VISIBLE);
                        statusText.setText("连接断开，3秒后重连...");
                    });
                    reconnectHandler.postDelayed(MainActivity.this::connectWebSocket, 3000);
                }
                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "WebSocket error", ex);
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.VISIBLE);
                        statusText.setText("连接错误");
                    });
                }
            };
            wsClient.connect();
        } catch (Exception e) {
            Log.e(TAG, "Connection failed", e);
            reconnectHandler.postDelayed(MainActivity.this::connectWebSocket, 3000);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        reconnectHandler.removeCallbacksAndMessages(null);
        if (wsClient != null) wsClient.close();
    }
}
