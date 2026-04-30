package com.poolar.controller;

import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ListView;
import android.widget.SimpleAdapter;
import android.widget.TextView;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import com.poolar.controller.model.Models;
import com.poolar.controller.network.ApiClient;
import com.poolar.controller.network.ServiceDiscovery;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class HomeFragment extends Fragment {
    private TextView connectionStatus, infoServer, infoCamera, infoMode;
    private Button btnStart, btnStop;
    private View cardMatch, cardTraining, cardChallenge;
    private Handler handler = new Handler(Looper.getMainLooper());
    private Runnable infoRefresher;

    // 回调给 MainActivity
    private MainActivity mainActivity() {
        return (MainActivity) requireActivity();
    }

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_home, container, false);

        connectionStatus = v.findViewById(R.id.connectionStatus);
        infoServer = v.findViewById(R.id.infoServer);
        infoCamera = v.findViewById(R.id.infoCamera);
        infoMode = v.findViewById(R.id.infoMode);
        btnStart = v.findViewById(R.id.btnStart);
        btnStop = v.findViewById(R.id.btnStop);
        cardMatch = v.findViewById(R.id.cardMatch);
        cardTraining = v.findViewById(R.id.cardTraining);
        cardChallenge = v.findViewById(R.id.cardChallenge);

        // 显示服务器信息
        SharedPreferences prefs = requireActivity().getSharedPreferences("prefs", 0);
        String host = prefs.getString("server_host", "192.168.0.35");
        int port = prefs.getInt("server_port", 8000);
        infoServer.setText("服务器: " + host + ":" + port);
        ApiClient.init(host);

        // 后台自动发现
        new ServiceDiscovery().discoverServer(new ServiceDiscovery.DiscoveryCallback() {
            @Override
            public void onFound(String foundHost, int foundPort) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        infoServer.setText("服务器: " + foundHost + ":" + foundPort);
                        prefs.edit().putString("server_host", foundHost)
                            .putInt("server_port", foundPort).apply();
                        ApiClient.init(foundHost);
                        mainActivity().ws().disconnect();
                        mainActivity().ws().connect(foundHost, foundPort, "/api/ws/phone");
                    });
                }
            }
            @Override
            public void onError(String message) {}
        });

        // 启动/停止
        btnStart.setOnClickListener(v2 -> ApiClient.control("start", ok ->
            Toast.makeText(getContext(), ok ? "系统已启动" : "启动失败", Toast.LENGTH_SHORT).show()));
        btnStop.setOnClickListener(v2 -> ApiClient.control("stop", ok ->
            Toast.makeText(getContext(), ok ? "系统已停止" : "停止失败", Toast.LENGTH_SHORT).show()));

        // 比赛模式 — 弹出姓名对话框
        cardMatch.setOnClickListener(v2 -> showMatchDialog(prefs));

        // 训练模式 — 弹出关卡选择对话框
        cardTraining.setOnClickListener(v2 -> showLevelDialog("training"));

        // 闯关模式 — 弹出关卡选择对话框
        cardChallenge.setOnClickListener(v2 -> showLevelDialog("challenge"));

        // 系统信息定时刷新
        infoRefresher = new Runnable() {
            @Override public void run() {
                ApiClient.getStatus(data -> {
                    if (data != null) {
                        infoServer.setText("服务器: " + host + ":" + port);
                        infoCamera.setText("摄像头: " + (data.optBoolean("camera", false) ? "正常" : "离线"));
                        infoMode.setText("模式: " + data.optString("mode", "idle"));
                    }
                });
                handler.postDelayed(this, 3000);
            }
        };
        handler.post(infoRefresher);
        return v;
    }

    private void showMatchDialog(SharedPreferences prefs) {
        View dialogView = LayoutInflater.from(getContext())
            .inflate(R.layout.dialog_player_names, null);
        EditText p1Input = dialogView.findViewById(R.id.player1Input);
        EditText p2Input = dialogView.findViewById(R.id.player2Input);
        CheckBox saveCheck = dialogView.findViewById(R.id.saveDefaultCheck);

        // 预填默认值
        p1Input.setText(prefs.getString("default_player1", ""));
        p2Input.setText(prefs.getString("default_player2", ""));

        AlertDialog dialog = new AlertDialog.Builder(getContext())
            .setView(dialogView)
            .setCancelable(true)
            .create();

        dialogView.findViewById(R.id.btnCancelMatch).setOnClickListener(v2 -> dialog.dismiss());
        dialogView.findViewById(R.id.btnConfirmMatch).setOnClickListener(v2 -> {
            String p1 = p1Input.getText().toString().trim();
            String p2 = p2Input.getText().toString().trim();
            if (p1.isEmpty()) p1 = "选手一";
            if (p2.isEmpty()) p2 = "选手二";

            if (saveCheck.isChecked()) {
                prefs.edit().putString("default_player1", p1)
                    .putString("default_player2", p2).apply();
            }

            ApiClient.setMode("match", ok -> {
                if (ok) {
                    mainActivity().setCurrentMode("match");
                    Toast.makeText(getContext(), "比赛开始: " + p1 + " vs " + p2, Toast.LENGTH_SHORT).show();
                    mainActivity().switchToProgressTab();
                }
            });
            dialog.dismiss();
        });
        dialog.show();
    }

    private void showLevelDialog(String mode) {
        ApiClient.getTrainingLevels(new ApiClient.ApiCallback<List<Models.TrainingLevel>>() {
            @Override
            public void onResult(List<Models.TrainingLevel> levels) {
                if (getActivity() == null || levels == null) return;
                getActivity().runOnUiThread(() -> {
                    View dialogView = LayoutInflater.from(getContext())
                        .inflate(R.layout.dialog_level_select, null);
                    ListView listView = dialogView.findViewById(R.id.levelListView);

                    List<Map<String, String>> items = new ArrayList<>();
                    for (Models.TrainingLevel lv : levels) {
                        Map<String, String> item = new HashMap<>();
                        item.put("title", lv.level + "档 · " + lv.name);
                        item.put("desc", lv.description + " (" + lv.drillCount + "题)");
                        items.add(item);
                    }
                    SimpleAdapter adapter = new SimpleAdapter(getContext(), items,
                        android.R.layout.simple_list_item_2,
                        new String[]{"title", "desc"},
                        new int[]{android.R.id.text1, android.R.id.text2});
                    listView.setAdapter(adapter);

                    AlertDialog dialog = new AlertDialog.Builder(getContext())
                        .setView(dialogView)
                        .setCancelable(true)
                        .create();

                    listView.setOnItemClickListener((parent, view, pos, id) -> {
                        String apiMode = mode.equals("challenge") ? "challenge" : "training";
                        ApiClient.setMode(apiMode, ok -> {
                            if (ok) {
                                ApiClient.selectLevel(pos + 1, new ApiClient.ApiCallback<Models.DrillSession>() {
                                    @Override
                                    public void onResult(Models.DrillSession result) {
                                        mainActivity().setCurrentMode(apiMode);
                                        getActivity().runOnUiThread(() -> {
                                            Toast.makeText(getContext(),
                                                "已选择: " + levels.get(pos).name, Toast.LENGTH_SHORT).show();
                                            mainActivity().switchToProgressTab();
                                        });
                                    }
                                    @Override
                                    public void onError(String error) {}
                                });
                            }
                        });
                        dialog.dismiss();
                    });

                    dialogView.findViewById(R.id.btnCancelLevel).setOnClickListener(v2 -> dialog.dismiss());
                    dialog.show();
                });
            }
            @Override
            public void onError(String error) {}
        });
    }

    // WebSocket 连接状态回调
    public void onWsConnected() {
        if (connectionStatus != null) {
            connectionStatus.setText(R.string.status_connected);
            connectionStatus.setTextColor(getResources().getColor(R.color.success));
        }
    }

    public void onWsDisconnected() {
        if (connectionStatus != null) {
            connectionStatus.setText(R.string.status_disconnected);
            connectionStatus.setTextColor(getResources().getColor(R.color.text_tertiary));
        }
    }

    public void onWsReconnecting() {
        if (connectionStatus != null) {
            connectionStatus.setText("🔄 重连中...");
            connectionStatus.setTextColor(getResources().getColor(R.color.accent));
        }
    }

    @Override
    public void onDestroyView() {
        super.onDestroyView();
        handler.removeCallbacks(infoRefresher);
    }
}
