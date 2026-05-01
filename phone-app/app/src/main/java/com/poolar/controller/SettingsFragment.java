package com.poolar.controller;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import com.google.gson.JsonObject;
import com.poolar.controller.network.ApiClient;
import com.poolar.controller.network.ServiceDiscovery;
import com.poolar.controller.network.WebSocketClient;

public class SettingsFragment extends Fragment {
    private EditText hostInput, portInput, defaultPlayer1, defaultPlayer2;
    private TextView calStatus, modelStatus;
    private Switch toggleCameraPreview, toggleProjectorPreview;
    private WebSocketClient cameraPreviewWs, projectorPreviewWs;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_settings, container, false);

        SharedPreferences prefs = requireActivity().getSharedPreferences("prefs", 0);

        // 服务器配置
        hostInput = v.findViewById(R.id.hostInput);
        portInput = v.findViewById(R.id.portInput);
        hostInput.setText(prefs.getString("server_host", "192.168.0.35"));
        portInput.setText(String.valueOf(prefs.getInt("server_port", 8000)));

        v.findViewById(R.id.btnSave).setOnClickListener(v2 -> saveAndReconnect(prefs));
        v.findViewById(R.id.btnDiscover).setOnClickListener(v2 -> discoverServer(prefs));

        // 预览开关
        toggleCameraPreview = v.findViewById(R.id.toggleCameraPreview);
        toggleProjectorPreview = v.findViewById(R.id.toggleProjectorPreview);
        toggleCameraPreview.setOnCheckedChangeListener((btn, on) -> togglePreview("camera", on));
        toggleProjectorPreview.setOnCheckedChangeListener((btn, on) -> togglePreview("projector", on));

        // 校准
        calStatus = v.findViewById(R.id.calStatus);
        v.findViewById(R.id.btnCalStart).setOnClickListener(v2 ->
            ApiClient.startCalibration(new ApiClient.ApiCallback<Void>() {
                @Override public void onResult(Void r) { calStatus.setText(R.string.cal_status_calibrating); }
                @Override public void onError(String e) { calStatus.setText(R.string.cal_status_start_failed); }
            }));
        v.findViewById(R.id.btnCalStop).setOnClickListener(v2 ->
            ApiClient.stopCalibration(new ApiClient.ApiCallback<Void>() {
                @Override public void onResult(Void r) { calStatus.setText(R.string.cal_status_stopped); }
                @Override public void onError(String e) {}
            }));

        // AI模型
        modelStatus = v.findViewById(R.id.modelStatus);
        v.findViewById(R.id.btnModelTrain).setOnClickListener(v2 ->
            ApiClient.post("/api/ai-train/start", null, ok ->
                Toast.makeText(getContext(), ok ? R.string.msg_ai_train_started : R.string.msg_ai_train_failed, Toast.LENGTH_SHORT).show()));
        v.findViewById(R.id.btnModelReset).setOnClickListener(v2 ->
            new android.app.AlertDialog.Builder(getContext())
                .setTitle(R.string.msg_reset_model_title)
                .setMessage(R.string.msg_reset_model_desc)
                .setPositiveButton(R.string.btn_confirm, (d, w) ->
                    ApiClient.post("/api/ai-train/reset", null, ok ->
                        Toast.makeText(getContext(), ok ? R.string.msg_model_reset : R.string.msg_model_reset_failed, Toast.LENGTH_SHORT).show()))
                .setNegativeButton(R.string.btn_cancel, null)
                .show());

        // 默认选手姓名
        defaultPlayer1 = v.findViewById(R.id.defaultPlayer1);
        defaultPlayer2 = v.findViewById(R.id.defaultPlayer2);
        defaultPlayer1.setText(prefs.getString("default_player1", ""));
        defaultPlayer2.setText(prefs.getString("default_player2", ""));
        v.findViewById(R.id.btnSavePlayers).setOnClickListener(v2 -> {
            prefs.edit().putString("default_player1", defaultPlayer1.getText().toString().trim())
                .putString("default_player2", defaultPlayer2.getText().toString().trim())
                .apply();
            Toast.makeText(getContext(), R.string.msg_saved, Toast.LENGTH_SHORT).show();
        });

        return v;
    }

    private void saveAndReconnect(SharedPreferences prefs) {
        String host = hostInput.getText().toString().trim();
        int port;
        try {
            port = Integer.parseInt(portInput.getText().toString().trim());
        } catch (NumberFormatException e) {
            Toast.makeText(getContext(), "端口格式错误", Toast.LENGTH_SHORT).show();
            return;
        }
        prefs.edit().putString("server_host", host).putInt("server_port", port).apply();
        ApiClient.init(host);
        MainActivity ma = (MainActivity) requireActivity();
        ma.ws().disconnect();
        ma.ws().connect(host, port, "/api/ws/phone");
        Toast.makeText(getContext(), "已保存并重连 " + host + ":" + port, Toast.LENGTH_SHORT).show();
    }

    private void discoverServer(SharedPreferences prefs) {
        new ServiceDiscovery().discoverServer(new ServiceDiscovery.DiscoveryCallback() {
            @Override public void onFound(String host, int port) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        hostInput.setText(host);
                        portInput.setText(String.valueOf(port));
                        saveAndReconnect(prefs);
                    });
                }
            }
            @Override public void onError(String msg) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() ->
                        Toast.makeText(getContext(), msg, Toast.LENGTH_SHORT).show());
                }
            }
        });
    }

    private void togglePreview(String which, boolean on) {
        SharedPreferences prefs = requireActivity().getSharedPreferences("prefs", 0);
        String host = prefs.getString("server_host", "192.168.0.35");
        int port = prefs.getInt("server_port", 8000);
        String path = "/api/ws/" + which + "-preview";

        if (on) {
            WebSocketClient ws = new WebSocketClient();
            ws.connect(host, port, path);
            if ("camera".equals(which)) cameraPreviewWs = ws;
            else projectorPreviewWs = ws;
        } else {
            WebSocketClient ws = "camera".equals(which) ? cameraPreviewWs : projectorPreviewWs;
            if (ws != null) { ws.disconnect(); }
        }
    }

    // WebSocket 消息（校准状态、模型状态更新）
    public void onWebSocketMessage(String type, JsonObject data) {
        if (!isAdded()) return;
        if ("calibration_status".equals(type) && data.has("status")) {
            calStatus.setText("状态: " + data.get("status").getAsString());
        }
        if ("model_status".equals(type)) {
            int shots = data.has("shot_count") ? data.get("shot_count").getAsInt() : 0;
            boolean trained = data.has("is_trained") && data.get("is_trained").getAsBoolean();
            modelStatus.setText("已采集: " + shots + " 杆 | 模型: " + (trained ? "✅ 已训练" : "未训练"));
        }
    }

    // 重连后刷新校准和模型状态
    public void refreshState() {
        if (!isAdded()) return;
        ApiClient.get("/calibration/status", data -> {
            if (data != null && isAdded() && calStatus != null) {
                String status = data.optString("status", "未知");
                getActivity().runOnUiThread(() -> calStatus.setText("状态: " + status));
            }
        });
        ApiClient.get("/model/status", data -> {
            if (data != null && isAdded() && modelStatus != null) {
                int shots = data.optInt("shot_count", 0);
                boolean trained = data.optBoolean("is_trained", false);
                getActivity().runOnUiThread(() ->
                    modelStatus.setText("已采集: " + shots + " 杆 | 模型: " + (trained ? "✅ 已训练" : "未训练")));
            }
        });
    }

    @Override
    public void onDestroyView() {
        super.onDestroyView();
        if (cameraPreviewWs != null) cameraPreviewWs.disconnect();
        if (projectorPreviewWs != null) projectorPreviewWs.disconnect();
    }
}
