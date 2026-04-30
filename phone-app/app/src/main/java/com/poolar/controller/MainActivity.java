package com.poolar.controller;

import android.content.SharedPreferences;
import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;
import androidx.fragment.app.Fragment;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.google.gson.JsonObject;
import com.poolar.controller.network.WebSocketClient;

public class MainActivity extends AppCompatActivity implements WebSocketClient.MessageListener {
    private static final String TAG = "PoolARController";

    private WebSocketClient wsClient;
    private HomeFragment homeFragment;
    private InProgressFragment inProgressFragment;
    private SettingsFragment settingsFragment;
    private Fragment activeFragment;
    private String currentMode = "idle";

    // 共享状态 — 各Fragment从这里读取，WebSocket更新
    public String currentMode() { return currentMode; }
    public void setCurrentMode(String mode) { this.currentMode = mode; }
    public WebSocketClient ws() { return wsClient; }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // 初始化 WebSocket
        SharedPreferences prefs = getSharedPreferences("prefs", 0);
        String host = prefs.getString("server_host", "192.168.0.35");
        int port = prefs.getInt("server_port", 8000);
        wsClient = new WebSocketClient();
        wsClient.addListener(this);
        wsClient.connect(host, port, "/api/ws/phone");

        // Fragment 复用
        homeFragment = new HomeFragment();
        inProgressFragment = new InProgressFragment();
        settingsFragment = new SettingsFragment();

        BottomNavigationView nav = findViewById(R.id.bottomNav);
        nav.setOnItemSelectedListener(item -> {
            int id = item.getItemId();
            if (id == R.id.nav_home) {
                switchTo(homeFragment);
            } else if (id == R.id.nav_progress) {
                switchTo(inProgressFragment);
            } else if (id == R.id.nav_settings) {
                switchTo(settingsFragment);
            } else {
                return false;
            }
            return true;
        });
        nav.setSelectedItemId(R.id.nav_home);
    }

    private void switchTo(Fragment frag) {
        if (activeFragment == frag) return;
        activeFragment = frag;
        getSupportFragmentManager().beginTransaction()
            .replace(R.id.fragmentContainer, frag).commit();
    }

    public void switchToProgressTab() {
        BottomNavigationView nav = findViewById(R.id.bottomNav);
        nav.setSelectedItemId(R.id.nav_progress);
    }

    // WebSocket 消息分发
    @Override
    public void onMessage(String type, JsonObject data) {
        // 转发给当前活跃的Fragment
        if (inProgressFragment != null) {
            inProgressFragment.onWebSocketMessage(type, data);
        }
        if (settingsFragment != null) {
            settingsFragment.onWebSocketMessage(type, data);
        }
    }

    @Override
    public void onConnected() {
        if (homeFragment != null) homeFragment.onWsConnected();
        // 重连后刷新状态
        if (inProgressFragment != null) inProgressFragment.refreshState();
        if (settingsFragment != null) settingsFragment.refreshState();
    }

    @Override
    public void onDisconnected() {
        if (homeFragment != null) homeFragment.onWsDisconnected();
    }

    @Override
    public void onReconnecting() {
        if (homeFragment != null) homeFragment.onWsReconnecting();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (wsClient != null) {
            wsClient.removeListener(this);
            wsClient.disconnect();
        }
    }
}
