package com.poolar.projector;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.Handler;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import java.net.URI;
import java.util.Locale;

public class MainActivity extends Activity implements TextToSpeech.OnInitListener {
    private ImageView projectionView;
    private TextView statusText;
    private WebSocketClient wsClient;
    private Handler reconnectHandler = new Handler();
    private TextToSpeech tts;
    private boolean ttsReady = false;
    private static final String TAG = "PoolARProjector";
    private static final String DEFAULT_SERVER = "ws://192.168.0.35:8000/api/ws/projector";

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
        statusText.setOnLongClickListener(v -> {
            showSettingsDialog();
            return true;
        });

        // Initialize TTS engine
        tts = new TextToSpeech(this, this);

        connectWebSocket();
    }

    // ─── TextToSpeech.OnInitListener ───────────────────────

    @Override
    public void onInit(int status) {
        if (status == TextToSpeech.SUCCESS) {
            int result = tts.setLanguage(Locale.CHINESE);
            if (result == TextToSpeech.LANG_MISSING_DATA
                || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                Log.w(TAG, "TTS: Chinese language not supported");
                showToast("TTS: 中文语音暂不支持");
            } else {
                ttsReady = true;
                Log.d(TAG, "TTS engine ready");
            }
        } else {
            Log.e(TAG, "TTS engine init failed");
        }
    }

    private void speak(String text) {
        if (ttsReady && tts != null) {
            tts.speak(text, TextToSpeech.QUEUE_ADD, null, null);
        }
    }

    // ─── Settings dialog ───────────────────────────────────

    private void showSettingsDialog() {
        SharedPreferences prefs = getSharedPreferences("prefs", MODE_PRIVATE);
        String currentUrl = prefs.getString("server_url", DEFAULT_SERVER);
        EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT);
        input.setText(currentUrl);
        input.setSelectAllOnFocus(true);
        new AlertDialog.Builder(this)
            .setTitle("设置服务器地址")
            .setMessage("当前: " + currentUrl)
            .setView(input)
            .setPositiveButton("连接", (d, w) -> {
                String url = input.getText().toString().trim();
                if (!url.isEmpty()) {
                    prefs.edit().putString("server_url", url).apply();
                    if (wsClient != null) wsClient.close();
                    statusText.setText("正在连接...");
                    connectWebSocket();
                }
            })
            .setNegativeButton("取消", null)
            .show();
    }

    // ─── WebSocket ─────────────────────────────────────────

    private void connectWebSocket() {
        String serverUrl = getSharedPreferences("prefs", MODE_PRIVATE)
            .getString("server_url", DEFAULT_SERVER);
        try {
            wsClient = new WebSocketClient(new URI(serverUrl)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    runOnUiThread(() -> {
                        statusText.setText("已连接，等待投影画面...");
                        statusText.setVisibility(View.VISIBLE);
                        Log.d(TAG, "Connected to server");
                    });
                }
                @Override
                public void onMessage(String message) {
                    try {
                        com.google.gson.JsonObject json = new com.google.gson.Gson()
                            .fromJson(message, com.google.gson.JsonObject.class);
                        String type = json.get("type").getAsString();

                        if ("projection".equals(type)) {
                            String base64 = json.get("image").getAsString();
                            byte[] imgBytes = Base64.decode(base64, Base64.DEFAULT);
                            final Bitmap bitmap = BitmapFactory.decodeByteArray(imgBytes, 0, imgBytes.length);
                            runOnUiThread(() -> {
                                projectionView.setImageBitmap(bitmap);
                                statusText.setVisibility(View.GONE);
                            });
                        } else if ("announce".equals(type)) {
                            // TTS announcement from backend announcer
                            String text = json.get("text").getAsString();
                            speak(text);
                            Log.d(TAG, "Announce: " + text);
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error processing message", e);
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

    // ─── Lifecycle ─────────────────────────────────────────

    @Override
    protected void onDestroy() {
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        reconnectHandler.removeCallbacksAndMessages(null);
        if (wsClient != null) wsClient.close();
        super.onDestroy();
    }

    private void showToast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }
}
