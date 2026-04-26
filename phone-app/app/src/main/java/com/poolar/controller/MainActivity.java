package com.poolar.controller;

import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import com.poolar.controller.network.ApiClient;
import com.poolar.controller.network.ServiceDiscovery;

public class MainActivity extends AppCompatActivity {
    private TextView connectionStatus;
    private ApiClient apiClient;
    private Button btnStart, btnStop, btnMatch, btnTraining, btnChallenge;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        connectionStatus = findViewById(R.id.connectionStatus);
        btnStart = findViewById(R.id.btnStart);
        btnStop = findViewById(R.id.btnStop);
        btnMatch = findViewById(R.id.btnMatchMode);
        btnTraining = findViewById(R.id.btnTrainingMode);
        btnChallenge = findViewById(R.id.btnChallengeMode);
        connectionStatus.setText("正在搜索服务器...");
        new ServiceDiscovery().discoverServer(new ServiceDiscovery.DiscoveryCallback() {
            @Override
            public void onFound(String host, int port) {
                apiClient = new ApiClient(host);
                runOnUiThread(() -> {
                    connectionStatus.setText("已连接: " + host);
                    connectionStatus.setTextColor(0xFF4CAF50);
                    enableButtons(true);
                });
            }
            @Override
            public void onError(String message) {
                runOnUiThread(() -> {
                    connectionStatus.setText("连接失败: " + message);
                    connectionStatus.setTextColor(0xFFF44336);
                });
            }
        });
        btnStart.setOnClickListener(v -> {
            if (apiClient != null) apiClient.startSystem(callback("系统已启动"));
        });
        btnStop.setOnClickListener(v -> {
            if (apiClient != null) apiClient.stopSystem(callback("系统已停止"));
        });
        btnMatch.setOnClickListener(v -> {
            if (apiClient != null) apiClient.setMode("match", modeCallback("比赛模式已启动"));
        });
        btnTraining.setOnClickListener(v -> {
            if (apiClient != null) apiClient.setMode("training", modeCallback("训练模式已启动"));
        });
        btnChallenge.setOnClickListener(v -> {
            if (apiClient != null) apiClient.setMode("challenge", modeCallback("闯关模式已启动"));
        });
    }

    private void enableButtons(boolean enabled) {
        btnStart.setEnabled(enabled);
        btnStop.setEnabled(enabled);
        btnMatch.setEnabled(enabled);
        btnTraining.setEnabled(enabled);
        btnChallenge.setEnabled(enabled);
    }

    private ApiClient.ApiCallback<Void> callback(String msg) {
        return new ApiClient.ApiCallback<Void>() {
            @Override public void onResult(Void result) { showToast(msg); }
            @Override public void onError(String error) { showToast("失败: " + error); }
        };
    }

    private ApiClient.ApiCallback<Object> modeCallback(String msg) {
        return new ApiClient.ApiCallback<Object>() {
            @Override public void onResult(Object result) { showToast(msg); }
            @Override public void onError(String error) { showToast("失败: " + error); }
        };
    }

    private void showToast(String message) {
        runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
    }
}
