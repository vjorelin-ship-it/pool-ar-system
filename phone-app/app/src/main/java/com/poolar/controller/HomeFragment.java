package com.poolar.controller;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import com.poolar.controller.network.ApiClient;
import com.poolar.controller.network.ServiceDiscovery;

public class HomeFragment extends Fragment {
    private TextView statusText, serverInfo;
    private Button btnStart, btnStop;
    private Button btnMatch, btnTraining, btnChallenge;
    private Handler handler = new Handler(Looper.getMainLooper());
    private Runnable statusRefresher;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_home, container, false);
        statusText = v.findViewById(R.id.statusText);
        serverInfo = v.findViewById(R.id.serverInfo);
        btnStart = v.findViewById(R.id.btnStart);
        btnStop = v.findViewById(R.id.btnStop);
        btnMatch = v.findViewById(R.id.btnMatch);
        btnTraining = v.findViewById(R.id.btnTraining);
        btnChallenge = v.findViewById(R.id.btnChallenge);

        // Show server info and init ApiClient singleton
        SharedPreferences prefs = requireActivity().getSharedPreferences("prefs", 0);
        String host = prefs.getString("server_host", "192.168.0.35");
        int port = prefs.getInt("server_port", 8000);
        serverInfo.setText("服务器: " + host + ":" + port);
        ApiClient.init(host);

        // Start auto-discovery in background
        new ServiceDiscovery().discoverServer(new ServiceDiscovery.DiscoveryCallback() {
            @Override
            public void onFound(String foundHost, int foundPort) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        serverInfo.setText("服务器: " + foundHost + ":" + foundPort);
                        prefs.edit().putString("server_host", foundHost)
                            .putInt("server_port", foundPort).apply();
                        ApiClient.init(foundHost);
                        Toast.makeText(getContext(), "发现服务器: " + foundHost, Toast.LENGTH_SHORT).show();
                    });
                }
            }
            @Override
            public void onError(String message) { /* silent */ }
        });

        // Mode cards
        btnMatch.setOnClickListener(v2 -> {
            ApiClient.setMode("match", ok -> {
                if (ok) Toast.makeText(getContext(), "已切换到比赛模式", Toast.LENGTH_SHORT).show();
            });
        });
        btnTraining.setOnClickListener(v2 -> {
            ApiClient.setMode("training", ok -> {
                if (ok) Toast.makeText(getContext(), "已切换到训练模式", Toast.LENGTH_SHORT).show();
            });
        });
        btnChallenge.setOnClickListener(v2 -> {
            ApiClient.setMode("challenge", ok -> {
                if (ok) Toast.makeText(getContext(), "已切换到闯关模式", Toast.LENGTH_SHORT).show();
            });
        });

        // Start/stop
        btnStart.setOnClickListener(v2 -> {
            ApiClient.control("start", ok -> {
                statusText.setText(ok ? "系统运行中" : "启动失败");
            });
        });
        btnStop.setOnClickListener(v2 -> {
            ApiClient.control("stop", ok -> {
                statusText.setText(ok ? "系统已停止" : "停止失败");
            });
        });

        // Periodic status refresh
        statusRefresher = new Runnable() {
            @Override public void run() {
                ApiClient.getStatus(data -> {
                    if (data != null) {
                        statusText.setText("运行中 · " + data.optString("mode", "idle") + " · " + data.optInt("ball_count", 0) + "球");
                    }
                });
                handler.postDelayed(this, 3000);
            }
        };
        handler.post(statusRefresher);
        return v;
    }

    @Override public void onDestroyView() {
        super.onDestroyView();
        handler.removeCallbacks(statusRefresher);
    }
}
