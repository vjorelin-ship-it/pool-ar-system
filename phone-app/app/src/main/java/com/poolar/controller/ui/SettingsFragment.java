package com.poolar.controller.ui;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.util.Base64;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import com.poolar.controller.R;
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import java.net.URI;

public class SettingsFragment extends Fragment {

    private EditText ipInput;
    private Button btnReconnect, btnCalibration, btnAiTrain, btnAiReset;
    private Button btnToggleCamera, btnToggleProjector;
    private TextView connStatus, calStatus, aiStatus, aiStats;
    private ImageView cameraPreview, projectorPreview;
    private static final int PORT = 8000;
    private static final String TAG = "Settings";
    private static final String PREFS_NAME = "prefs";
    private static final String KEY_SERVER_IP = "server_ip";
    private String currentHost;
    private WebSocketClient cameraWs, projectorWs;
    private boolean cameraOn = false, projectorOn = false;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container,
                             Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_settings, container, false);

        ipInput = v.findViewById(R.id.settings_ip);
        btnReconnect = v.findViewById(R.id.btn_reconnect);
        connStatus = v.findViewById(R.id.settings_conn_status);
        btnToggleCamera = v.findViewById(R.id.btn_toggle_camera);
        btnToggleProjector = v.findViewById(R.id.btn_toggle_projector);
        cameraPreview = v.findViewById(R.id.camera_preview);
        projectorPreview = v.findViewById(R.id.projector_preview);
        calStatus = v.findViewById(R.id.calibration_status);
        btnCalibration = v.findViewById(R.id.btn_calibration);
        aiStatus = v.findViewById(R.id.ai_model_status);
        aiStats = v.findViewById(R.id.ai_model_stats);
        btnAiTrain = v.findViewById(R.id.btn_ai_train);
        btnAiReset = v.findViewById(R.id.btn_ai_reset);

        // Load saved IP
        String savedIp = getActivity().getSharedPreferences(PREFS_NAME, 0)
            .getString(KEY_SERVER_IP, "192.168.0.35");
        ipInput.setText(savedIp);
        currentHost = savedIp;

        btnReconnect.setOnClickListener(view -> {
            String ip = ipInput.getText().toString().trim();
            if (!ip.isEmpty()) {
                // Persist IP
                getActivity().getSharedPreferences(PREFS_NAME, 0)
                    .edit().putString(KEY_SERVER_IP, ip).apply();
                currentHost = ip;
                connStatus.setText("已连接: " + ip);
                connStatus.setTextColor(0xFF4CAF50);
                showToast("重新连接: " + ip);
            }
        });

        btnToggleCamera.setOnClickListener(view -> {
            if (!ensureHost()) return;
            cameraOn = !cameraOn;
            if (cameraOn) {
                btnToggleCamera.setText("关闭");
                btnToggleCamera.setBackgroundTintList(
                    android.content.res.ColorStateList.valueOf(0xFF333333));
                cameraPreview.setVisibility(View.VISIBLE);
                connectCameraPreview();
            } else {
                btnToggleCamera.setText("开启");
                btnToggleCamera.setBackgroundTintList(
                    android.content.res.ColorStateList.valueOf(0xFF1b5e20));
                cameraPreview.setVisibility(View.GONE);
                disconnectCameraPreview();
            }
        });

        btnToggleProjector.setOnClickListener(view -> {
            if (!ensureHost()) return;
            projectorOn = !projectorOn;
            if (projectorOn) {
                btnToggleProjector.setText("关闭");
                btnToggleProjector.setBackgroundTintList(
                    android.content.res.ColorStateList.valueOf(0xFF333333));
                projectorPreview.setVisibility(View.VISIBLE);
                connectProjectorPreview();
            } else {
                btnToggleProjector.setText("开启");
                btnToggleProjector.setBackgroundTintList(
                    android.content.res.ColorStateList.valueOf(0xFF1b5e20));
                projectorPreview.setVisibility(View.GONE);
                disconnectProjectorPreview();
            }
        });

        btnCalibration.setOnClickListener(view -> {
            if (!ensureHost()) return;
            String text = btnCalibration.getText().toString();
            if (text.contains("开始")) {
                btnCalibration.setText("🎯 停止校准");
                calStatus.setText("🎯 校准中...");
                calStatus.setTextColor(0xFFFF9800);
                sendRequest("/api/calibration/start", true);
            } else {
                btnCalibration.setText("🎯 开始校准");
                calStatus.setText("🎯 校准状态: 未校准");
                calStatus.setTextColor(0xFF888888);
                sendRequest("/api/calibration/stop", false);
            }
        });

        btnAiTrain.setOnClickListener(view -> {
            if (!ensureHost()) return;
            sendAiTrainRequest("/api/ai-train/start");
        });

        btnAiReset.setOnClickListener(view -> {
            aiStatus.setText("未训练");
            aiStatus.setTextColor(0xFF888888);
            aiStats.setText("已采集 0 杆");
            showToast("模型已重置");
        });

        return v;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        disconnectCameraPreview();
        disconnectProjectorPreview();
    }

    // ─── Helpers ───────────────────────────────────────

    private boolean ensureHost() {
        currentHost = ipInput.getText().toString().trim();
        if (currentHost.isEmpty()) {
            showToast("请输入服务器IP");
            return false;
        }
        return true;
    }

    // ─── Camera Preview WebSocket ──────────────────────

    private void connectCameraPreview() {
        String wsUrl = "ws://" + currentHost + ":" + PORT + "/api/ws/camera-preview";
        try {
            cameraWs = new WebSocketClient(new URI(wsUrl)) {
                @Override public void onOpen(ServerHandshake h) {
                    Log.d(TAG, "Camera preview connected"); }
                @Override public void onClose(int c, String r, boolean rm) {
                    Log.d(TAG, "Camera preview closed"); }
                @Override public void onError(Exception e) {
                    Log.e(TAG, "Camera preview error", e); }
                @Override
                public void onMessage(String message) {
                    try {
                        com.google.gson.JsonObject json = new com.google.gson.Gson()
                            .fromJson(message, com.google.gson.JsonObject.class);
                        if ("camera_preview".equals(json.get("type").getAsString())) {
                            String b64 = json.get("image").getAsString();
                            byte[] img = Base64.decode(b64, Base64.DEFAULT);
                            Bitmap bitmap = BitmapFactory.decodeByteArray(img, 0, img.length);
                            if (bitmap != null && getActivity() != null) {
                                getActivity().runOnUiThread(() ->
                                    cameraPreview.setImageBitmap(bitmap));
                            }
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Camera preview decode error", e);
                    }
                }
            };
            cameraWs.connect();
        } catch (Exception e) {
            Log.e(TAG, "Camera preview failed", e);
        }
    }

    private void disconnectCameraPreview() {
        if (cameraWs != null) { cameraWs.close(); cameraWs = null; }
    }

    // ─── Projector Preview WebSocket ───────────────────

    private void connectProjectorPreview() {
        String wsUrl = "ws://" + currentHost + ":" + PORT + "/api/ws/projector-preview";
        try {
            projectorWs = new WebSocketClient(new URI(wsUrl)) {
                @Override public void onOpen(ServerHandshake h) {
                    Log.d(TAG, "Projector preview connected"); }
                @Override public void onClose(int c, String r, boolean rm) {
                    Log.d(TAG, "Projector preview closed"); }
                @Override public void onError(Exception e) {
                    Log.e(TAG, "Projector preview error", e); }
                @Override
                public void onMessage(String message) {
                    try {
                        com.google.gson.JsonObject json = new com.google.gson.Gson()
                            .fromJson(message, com.google.gson.JsonObject.class);
                        if ("projection".equals(json.get("type").getAsString())) {
                            String b64 = json.get("image").getAsString();
                            byte[] img = Base64.decode(b64, Base64.DEFAULT);
                            Bitmap bitmap = BitmapFactory.decodeByteArray(img, 0, img.length);
                            if (bitmap != null && getActivity() != null) {
                                getActivity().runOnUiThread(() ->
                                    projectorPreview.setImageBitmap(bitmap));
                            }
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Projector preview decode error", e);
                    }
                }
            };
            projectorWs.connect();
        } catch (Exception e) {
            Log.e(TAG, "Projector preview failed", e);
        }
    }

    private void disconnectProjectorPreview() {
        if (projectorWs != null) { projectorWs.close(); projectorWs = null; }
    }

    // ─── Calibration API ───────────────────────────────

    private void sendAiTrainRequest(String path) {
        new Thread(() -> {
            try {
                java.net.URL url = new java.net.URL("http://" + currentHost + ":" + PORT + path);
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setConnectTimeout(3000);
                int code = conn.getResponseCode();
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        if (code == 200) {
                            aiStatus.setText("训练中...");
                            aiStatus.setTextColor(0xFFFF9800);
                            btnAiTrain.setText("停止AI训练");
                            showToast("AI训练已启动，请按投影提示击球");
                        } else {
                            showToast("启动失败 (" + code + ")");
                        }
                    });
                }
            } catch (Exception e) {
                if (getActivity() != null)
                    getActivity().runOnUiThread(() ->
                        showToast("请求失败: " + e.getMessage()));
            }
        }).start();
    }

    private void sendRequest(String path, boolean starting) {
        new Thread(() -> {
            try {
                java.net.URL url = new java.net.URL("http://" + currentHost + ":" + PORT + path);
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setConnectTimeout(3000);
                int code = conn.getResponseCode();
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        showToast((starting ? "校准已启动" : "校准已停止") + " (" + code + ")");
                        if (!starting) {
                            calStatus.setText("🎯 校准已停止");
                            calStatus.setTextColor(0xFF888888);
                        }
                    });
                }
            } catch (Exception e) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        showToast("请求失败: " + e.getMessage());
                        if (starting) {
                            btnCalibration.setText("🎯 开始校准");
                            calStatus.setText("🎯 连接失败");
                            calStatus.setTextColor(0xFFF44336);
                        }
                    });
                }
            }
        }).start();
    }

    private void showToast(String msg) {
        if (getActivity() != null)
            getActivity().runOnUiThread(() ->
                Toast.makeText(getActivity(), msg, Toast.LENGTH_SHORT).show());
    }
}
