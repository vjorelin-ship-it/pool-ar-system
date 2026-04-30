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

import com.google.gson.JsonObject;
import com.google.gson.Gson;

import java.net.URI;
import java.util.Locale;

public class MainActivity extends Activity implements TextToSpeech.OnInitListener {
    private ImageView projectionView;
    private TextView statusText;
    private WebSocketClient wsProjectorClient;
    private WebSocketClient wsCameraClient;
    private Handler reconnectHandler = new Handler();
    private TextToSpeech tts;
    private boolean ttsReady = false;
    private CameraCapture cameraCapture;
    private Gson gson = new Gson();
    private int frameSkipCounter = 0;
    private static final int FRAME_SKIP = 3;
    private static final String TAG = "PoolARProjector";
    private static final String DEFAULT_HOST = "192.168.0.35";
    private static final int DEFAULT_PORT = 8000;

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

        tts = new TextToSpeech(this, this);

        startCameraCapture();
        connectProjectorWebSocket();
        connectCameraWebSocket();
    }

    // ─── Camera ──────────────────────────────────────────────

    private void startCameraCapture() {
        cameraCapture = new CameraCapture(this, (jpegData, timestamp) -> {
            frameSkipCounter++;
            if (frameSkipCounter % FRAME_SKIP != 0) return;

            if (wsCameraClient != null && wsCameraClient.isOpen()) {
                try {
                    String b64 = Base64.encodeToString(jpegData, Base64.NO_WRAP);
                    JsonObject msg = new JsonObject();
                    msg.addProperty("type", "camera_frame");
                    msg.addProperty("width", 2560);
                    msg.addProperty("height", 1440);
                    msg.addProperty("timestamp", timestamp);
                    msg.addProperty("frame_id", frameSkipCounter / FRAME_SKIP);
                    msg.addProperty("data", b64);
                    wsCameraClient.send(gson.toJson(msg));
                } catch (Exception e) {
                    Log.e(TAG, "Camera send error", e);
                }
            }
        });
        cameraCapture.start();
    }

    // ─── TTS ─────────────────────────────────────────────────

    @Override
    public void onInit(int status) {
        if (status == TextToSpeech.SUCCESS) {
            int result = tts.setLanguage(Locale.CHINESE);
            if (result == TextToSpeech.LANG_MISSING_DATA
                || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                Log.w(TAG, "TTS: Chinese not supported");
            } else {
                ttsReady = true;
                Log.d(TAG, "TTS ready");
            }
        }
    }

    private void speak(String text) {
        if (ttsReady && tts != null) {
            tts.speak(text, TextToSpeech.QUEUE_ADD, null, null);
        }
    }

    // ─── Settings ────────────────────────────────────────────

    private String host() {
        return getSharedPreferences("prefs", MODE_PRIVATE)
            .getString("server_host", DEFAULT_HOST);
    }

    private int port() {
        return getSharedPreferences("prefs", MODE_PRIVATE)
            .getInt("server_port", DEFAULT_PORT);
    }

    private void showSettingsDialog() {
        String current = "ws://" + host() + ":" + port();
        EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT);
        input.setText(current);
        input.setSelectAllOnFocus(true);
        new AlertDialog.Builder(this)
            .setTitle("设置服务器地址")
            .setMessage("当前: " + current)
            .setView(input)
            .setPositiveButton("连接", (d, w) -> {
                String url = input.getText().toString().trim();
                if (!url.isEmpty()) {
                    try {
                        URI uri = new URI(url);
                        getSharedPreferences("prefs", MODE_PRIVATE)
                            .edit()
                            .putString("server_host", uri.getHost())
                            .putInt("server_port", uri.getPort() <= 0 ? DEFAULT_PORT : uri.getPort())
                            .apply();
                    } catch (Exception e) { Log.e(TAG, "Invalid URL", e); }
                    reconnectAll();
                }
            })
            .setNegativeButton("取消", null)
            .show();
    }

    private void reconnectAll() {
        if (wsProjectorClient != null) wsProjectorClient.close();
        if (wsCameraClient != null) wsCameraClient.close();
        statusText.setText("正在重连...");
        connectProjectorWebSocket();
        connectCameraWebSocket();
    }

    // ─── Projector WebSocket ─────────────────────────────────

    private void connectProjectorWebSocket() {
        String url = "ws://" + host() + ":" + port() + "/api/ws/projector";
        try {
            wsProjectorClient = new WebSocketClient(new URI(url)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    runOnUiThread(() -> {
                        statusText.setText("投影已连接");
                        statusText.setVisibility(View.VISIBLE);
                    });
                }
                @Override
                public void onMessage(String message) {
                    try {
                        JsonObject json = gson.fromJson(message, JsonObject.class);
                        String type = json.get("type").getAsString();
                        if ("projection".equals(type)) {
                            byte[] imgBytes = Base64.decode(
                                json.get("image").getAsString(), Base64.DEFAULT);
                            final Bitmap bitmap = BitmapFactory.decodeByteArray(
                                imgBytes, 0, imgBytes.length);
                            runOnUiThread(() -> {
                                projectionView.setImageBitmap(bitmap);
                                statusText.setVisibility(View.GONE);
                            });
                        } else if ("announce".equals(type)) {
                            speak(json.get("text").getAsString());
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Message error", e);
                    }
                }
                @Override
                public void onClose(int code, String reason, boolean remote) {
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.VISIBLE);
                        statusText.setText("投影断开，3秒后重连");
                    });
                    reconnectHandler.postDelayed(
                        MainActivity.this::connectProjectorWebSocket, 3000);
                }
                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "Projector WS error", ex);
                }
            };
            wsProjectorClient.connect();
        } catch (Exception e) {
            Log.e(TAG, "Projector connect failed", e);
            reconnectHandler.postDelayed(
                MainActivity.this::connectProjectorWebSocket, 3000);
        }
    }

    // ─── Camera Upload WebSocket ─────────────────────────────

    private void connectCameraWebSocket() {
        String url = "ws://" + host() + ":" + port() + "/api/ws/camera-upload";
        try {
            wsCameraClient = new WebSocketClient(new URI(url)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    Log.d(TAG, "Camera upload connected");
                    runOnUiThread(() -> Toast.makeText(MainActivity.this,
                        "摄像头已连接", Toast.LENGTH_SHORT).show());
                }
                @Override
                public void onMessage(String message) {}
                @Override
                public void onClose(int code, String reason, boolean remote) {
                    Log.w(TAG, "Camera upload closed: " + reason);
                    reconnectHandler.postDelayed(
                        MainActivity.this::connectCameraWebSocket, 3000);
                }
                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "Camera upload WS error", ex);
                }
            };
            wsCameraClient.connect();
        } catch (Exception e) {
            Log.e(TAG, "Camera connect failed", e);
            reconnectHandler.postDelayed(
                MainActivity.this::connectCameraWebSocket, 3000);
        }
    }

    // ─── Lifecycle ───────────────────────────────────────────

    @Override
    protected void onDestroy() {
        if (cameraCapture != null) cameraCapture.stop();
        if (tts != null) { tts.stop(); tts.shutdown(); }
        reconnectHandler.removeCallbacksAndMessages(null);
        if (wsProjectorClient != null) wsProjectorClient.close();
        if (wsCameraClient != null) wsCameraClient.close();
        super.onDestroy();
    }
}
