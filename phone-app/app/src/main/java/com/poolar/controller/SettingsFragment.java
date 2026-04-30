package com.poolar.controller;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import com.poolar.controller.network.ApiClient;
import com.poolar.controller.network.ServiceDiscovery;

public class SettingsFragment extends Fragment {
    private EditText hostInput, portInput;
    private TextView calStatusText, modelStatusText;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_settings, container, false);

        SharedPreferences prefs = requireActivity().getSharedPreferences("prefs", 0);
        hostInput = v.findViewById(R.id.hostInput);
        portInput = v.findViewById(R.id.portInput);
        hostInput.setText(prefs.getString("server_host", "192.168.0.35"));
        portInput.setText(String.valueOf(prefs.getInt("server_port", 8000)));

        v.findViewById(R.id.btnSave).setOnClickListener(v2 -> {
            String host = hostInput.getText().toString().trim();
            int port = Integer.parseInt(portInput.getText().toString().trim());
            prefs.edit()
                .putString("server_host", host)
                .putInt("server_port", port)
                .apply();
            ApiClient.init(host);
            Toast.makeText(getContext(), "已保存", Toast.LENGTH_SHORT).show();
        });

        v.findViewById(R.id.btnDiscover).setOnClickListener(v2 -> {
            new ServiceDiscovery().discoverServer(new ServiceDiscovery.DiscoveryCallback() {
                @Override
                public void onFound(String host, int port) {
                    if (getActivity() != null) {
                        getActivity().runOnUiThread(() -> {
                            hostInput.setText(host);
                            portInput.setText(String.valueOf(port));
                            prefs.edit().putString("server_host", host)
                                .putInt("server_port", port).apply();
                            ApiClient.init(host);
                            Toast.makeText(getContext(), "发现服务器: " + host, Toast.LENGTH_SHORT).show();
                        });
                    }
                }
                @Override
                public void onError(String message) {
                    if (getActivity() != null) {
                        getActivity().runOnUiThread(() ->
                            Toast.makeText(getContext(), message, Toast.LENGTH_SHORT).show());
                    }
                }
            });
        });

        // Calibration
        calStatusText = v.findViewById(R.id.calStatus);
        v.findViewById(R.id.btnCalStart).setOnClickListener(v2 -> {
            ApiClient.post("/calibration/start", null, ok -> {
                calStatusText.setText("校准中...");
            });
        });
        v.findViewById(R.id.btnCalStop).setOnClickListener(v2 -> {
            ApiClient.post("/calibration/stop", null, ok -> {
                ApiClient.get("/calibration/status", data -> {
                    calStatusText.setText(data != null ? data.optString("status", "已停止") : "已停止");
                });
            });
        });

        // Model status
        modelStatusText = v.findViewById(R.id.modelStatus);
        v.findViewById(R.id.btnModelStatus).setOnClickListener(v2 -> {
            ApiClient.get("/model/status", data -> {
                if (data != null) {
                    int paramCount = data.optInt("param_count", 0);
                    boolean isTrained = data.optBoolean("is_trained", false);
                    modelStatusText.setText("参数: " + (paramCount / 1e6) + "M"
                        + " | 训练: " + (isTrained ? "是" : "否"));
                }
            });
        });

        // Collector control
        v.findViewById(R.id.btnCollectStart).setOnClickListener(v2 -> {
            ApiClient.post("/collector/start", null, ok -> {
                Toast.makeText(getContext(), ok ? "采集已开始" : "失败", Toast.LENGTH_SHORT).show();
            });
        });
        v.findViewById(R.id.btnCollectStop).setOnClickListener(v2 -> {
            ApiClient.post("/collector/stop", null, ok -> {
                Toast.makeText(getContext(), ok ? "采集已停止" : "失败", Toast.LENGTH_SHORT).show();
            });
        });

        return v;
    }
}
