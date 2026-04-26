package com.poolar.controller.ui;

import android.os.Bundle;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.fragment.app.Fragment;

import android.app.AlertDialog;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.reflect.TypeToken;
import com.poolar.controller.MainActivity;
import com.poolar.controller.R;
import com.poolar.controller.model.Models;
import com.poolar.controller.network.ApiClient;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import java.net.URI;

public class ActiveFragment extends Fragment {

    private static final String TAG = "ActiveFragment";
    private static final int PORT = 8000;

    // Common views
    private TextView idleText;
    private LinearLayout matchView, trainingView;

    // Match views
    private TextView p1Name, p1Score, p1Balls, p1Turn;
    private TextView p2Name, p2Score, p2Balls, p2Turn;
    private TextView matchEvents;
    private Button btnSwitchTurn;
    private android.widget.ImageView tableView;

    // Training views
    private TextView trainingTitle, drillLevel, drillProgress;
    private TextView drillDescription, drillPositions;
    private TextView placementStatus, shotFeedback, trainingStats;
    private Button btnSelectLevel;

    private WebSocketClient wsClient;
    private Gson gson = new com.google.gson.GsonBuilder()
        .setFieldNamingPolicy(com.google.gson.FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
        .create();
    private String currentHost;
    private boolean intentionalDisconnect = false;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container,
                             Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_active, container, false);

        // Common
        idleText = v.findViewById(R.id.idle_text);

        // Match
        matchView = v.findViewById(R.id.match_view);
        p1Name = v.findViewById(R.id.p1_name);
        p1Score = v.findViewById(R.id.p1_score);
        p1Balls = v.findViewById(R.id.p1_balls);
        p1Turn = v.findViewById(R.id.p1_turn);
        p2Name = v.findViewById(R.id.p2_name);
        p2Score = v.findViewById(R.id.p2_score);
        p2Balls = v.findViewById(R.id.p2_balls);
        p2Turn = v.findViewById(R.id.p2_turn);
        matchEvents = v.findViewById(R.id.match_events);
        btnSwitchTurn = v.findViewById(R.id.btn_switch_turn);
        tableView = v.findViewById(R.id.table_view);

        // Training
        trainingView = v.findViewById(R.id.training_view);
        trainingTitle = v.findViewById(R.id.training_title);
        drillLevel = v.findViewById(R.id.drill_level);
        drillProgress = v.findViewById(R.id.drill_progress);
        drillDescription = v.findViewById(R.id.drill_description);
        drillPositions = v.findViewById(R.id.drill_positions);
        placementStatus = v.findViewById(R.id.placement_status);
        shotFeedback = v.findViewById(R.id.shot_feedback);
        trainingStats = v.findViewById(R.id.training_stats);
        btnSelectLevel = v.findViewById(R.id.btn_select_level);

        btnSwitchTurn.setOnClickListener(view -> switchTurn());
        btnSelectLevel.setOnClickListener(view -> {
            showLevelSelectionDialog();
        });

        return v;
    }

    @Override
    public void onResume() {
        super.onResume();
        MainActivity activity = (MainActivity) getActivity();
        if (activity != null) {
            updateContent(activity.getCurrentMode(), null);
        }
        if (wsClient == null || !wsClient.isOpen()) {
            intentionalDisconnect = false;
            connectWebSocket();
        }
    }

    @Override
    public void onPause() {
        super.onPause();
        disconnectWebSocket();
    }

    private void connectWebSocket() {
        MainActivity activity = (MainActivity) getActivity();
        if (activity == null) return;

        // Try to get host from shared prefs or default
        if (currentHost == null) {
            currentHost = activity
                .getSharedPreferences("prefs", 0)
                .getString("server_ip", "192.168.0.35");
        }

        String wsUrl = "ws://" + currentHost + ":" + PORT + "/api/ws/phone";
        try {
            wsClient = new WebSocketClient(new URI(wsUrl)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    Log.d(TAG, "WebSocket connected");
                }

                @Override
                public void onMessage(String message) {
                    try {
                        JsonObject json = gson.fromJson(message, JsonObject.class);
                        String type = json.get("type").getAsString();
                        switch (type) {
                            case "score_update":
                                handleScoreUpdate(json.getAsJsonObject("score"));
                                break;
                            case "pocket_event":
                                handlePocketEvent(json.getAsJsonObject("data"));
                                break;
                            case "announce":
                                final String announceText = json.get("text").getAsString();
                                if (getActivity() != null) {
                                    getActivity().runOnUiThread(() -> {
                                        if (matchView.getVisibility() == View.VISIBLE) {
                                            matchEvents.setText(announceText);
                                        } else if (trainingView.getVisibility() == View.VISIBLE) {
                                            shotFeedback.setText(announceText);
                                            shotFeedback.setVisibility(View.VISIBLE);
                                        }
                                    });
                                }
                                break;
                            case "shot_result":
                                handleShotResult(json.getAsJsonObject("data"));
                                break;
                            case "placement_result":
                                handlePlacementResult(json.getAsJsonObject("data"));
                                break;
                            case "table_state":
                                handleTableState(json.getAsJsonObject("data"));
                                break;
                            case "drill_info":
                                handleDrillInfo(json.getAsJsonObject("data"));
                                break;
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "WS message error", e);
                    }
                }

                @Override
                public void onClose(int code, String reason, boolean remote) {
                    Log.d(TAG, "WebSocket closed");
                    if (!intentionalDisconnect) {
                        View v = getView();
                        if (v != null) {
                            v.postDelayed(ActiveFragment.this::connectWebSocket, 3000);
                        }
                    }
                }

                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "WebSocket error", ex);
                }
            };
            wsClient.connect();
        } catch (Exception e) {
            Log.e(TAG, "WS connection failed", e);
        }
    }

    private void disconnectWebSocket() {
        intentionalDisconnect = true;
        if (wsClient != null) {
            wsClient.close();
            wsClient = null;
        }
    }

    public void updateContent(String mode, String host) {
        if (host != null) currentHost = host;
        MainActivity activity = (MainActivity) getActivity();
        if (activity == null) return;

        // Hide all views first
        idleText.setVisibility(View.GONE);
        matchView.setVisibility(View.GONE);
        trainingView.setVisibility(View.GONE);

        if (mode == null || mode.equals("idle")) {
            idleText.setVisibility(View.VISIBLE);
            return;
        }

        if (mode.equals("match")) {
            matchView.setVisibility(View.VISIBLE);
            p1Name.setText(activity.getPlayer1Name());
            p2Name.setText(activity.getPlayer2Name());
            p1Balls.setText("--");
            p2Balls.setText("--");
            updateTurnIndicator(1);
        } else if (mode.equals("training") || mode.equals("challenge")) {
            trainingView.setVisibility(View.VISIBLE);
            trainingTitle.setText(mode.equals("challenge") ? "⭐ 闯关模式" : "🎯 训练模式");
            drillLevel.setText("请选择关卡");
            drillProgress.setText("");
            drillDescription.setText("点击下方「选择关卡」按钮开始");
            drillPositions.setText("");
            placementStatus.setVisibility(View.GONE);
            shotFeedback.setVisibility(View.GONE);
        }

        // Reconnect with new mode context
        disconnectWebSocket();
        connectWebSocket();
    }

    // ─── Level selection ───────────────────────────────

    private void showLevelSelectionDialog() {
        if (currentHost == null) {
            Toast.makeText(getActivity(), "请先连接服务器", Toast.LENGTH_SHORT).show();
            return;
        }

        // Fetch levels from API
        new Thread(() -> {
            try {
                java.net.URL url = new java.net.URL("http://" + currentHost + ":" + PORT + "/api/training/levels");
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                java.io.BufferedReader reader = new java.io.BufferedReader(
                    new java.io.InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
                reader.close();

                java.util.List<Models.TrainingLevel> levels = gson.fromJson(
                    response.toString(),
                    new TypeToken<java.util.List<Models.TrainingLevel>>(){}.getType()
                );

                if (getActivity() == null) return;
                getActivity().runOnUiThread(() -> showLevelDialog(levels));
            } catch (Exception e) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() ->
                        Toast.makeText(getActivity(), "获取关卡失败: " + e.getMessage(),
                            Toast.LENGTH_SHORT).show());
                }
            }
        }).start();
    }

    private void showLevelDialog(java.util.List<Models.TrainingLevel> levels) {
        AlertDialog.Builder builder = new AlertDialog.Builder(getContext());
        builder.setTitle("选择训练关卡");

        String[] names = new String[levels.size()];
        for (int i = 0; i < levels.size(); i++) {
            Models.TrainingLevel lv = levels.get(i);
            names[i] = lv.name + " (" + lv.drillCount + "题) " + lv.description;
        }

        builder.setItems(names, (dialog, which) -> {
            Models.TrainingLevel selected = levels.get(which);
            selectLevel(selected.level);
        });
        builder.setNegativeButton("取消", null);
        builder.show();
    }

    private void selectLevel(int level) {
        if (currentHost == null) return;
        new Thread(() -> {
            try {
                java.net.URL url = new java.net.URL(
                    "http://" + currentHost + ":" + PORT + "/api/training/select-level?level=" + level);
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                int code = conn.getResponseCode();
                java.io.BufferedReader reader = new java.io.BufferedReader(
                    new java.io.InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
                reader.close();

                if (getActivity() == null) return;
                getActivity().runOnUiThread(() -> {
                    Toast.makeText(getActivity(), "已选择第" + level + "档", Toast.LENGTH_SHORT).show();
                    updateDrillDisplay(response.toString());
                });
            } catch (Exception e) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() ->
                        Toast.makeText(getActivity(), "选择关卡失败", Toast.LENGTH_SHORT).show());
                }
            }
        }).start();
    }

    private void updateDrillDisplay(String json) {
        try {
            JsonObject data = gson.fromJson(json, JsonObject.class);
            if (data.has("drill")) {
                JsonObject drill = data.getAsJsonObject("drill");
                String desc = drill.get("description").getAsString();
                drillDescription.setText("📝 " + desc);

                StringBuilder pos = new StringBuilder();
                if (drill.has("cue_pos")) {
                    var arr = drill.getAsJsonArray("cue_pos");
                    pos.append("● 白球: (").append(arr.get(0).getAsDouble())
                       .append(", ").append(arr.get(1).getAsDouble()).append(")\n");
                }
                if (drill.has("target_pos")) {
                    var arr = drill.getAsJsonArray("target_pos");
                    pos.append("○ 目标: (").append(arr.get(0).getAsDouble())
                       .append(", ").append(arr.get(1).getAsDouble()).append(")");
                }
                drillPositions.setText(pos.toString());
            }
            if (data.has("progress")) {
                JsonObject p = data.getAsJsonObject("progress");
                drillLevel.setText("档位: " + p.get("level_name").getAsString());
                drillProgress.setText("第 " + p.get("drill").getAsString() +
                    " / " + p.get("total_drills").getAsString() + " 题");
            }
            placementStatus.setVisibility(View.GONE);
            shotFeedback.setVisibility(View.GONE);
        } catch (Exception e) {
            drillDescription.setText("解析失败");
        }
    }

    // ─── Match updates ─────────────────────────────────

    private String groupLabel(String group) {
        if (group == null || group.isEmpty()) return "--";
        if (group.equals("solids")) return "纯色";
        if (group.equals("stripes")) return "花色";
        return group;
    }

    private void handleScoreUpdate(JsonObject score) {
        if (getActivity() == null) return;
        getActivity().runOnUiThread(() -> {
            p1Score.setText(score.get("player1_score").getAsString());
            p2Score.setText(score.get("player2_score").getAsString());
            int current = score.get("current_player").getAsInt();
            updateTurnIndicator(current);

            // Ball type info
            String p1g = score.has("player1_balls") ? score.get("player1_balls").getAsString() : "";
            String p2g = score.has("player2_balls") ? score.get("player2_balls").getAsString() : "";
            int p1rem = score.has("p1_remaining") ? score.get("p1_remaining").getAsInt() : 0;
            int p2rem = score.has("p2_remaining") ? score.get("p2_remaining").getAsInt() : 0;
            p1Balls.setText(groupLabel(p1g) + " 剩" + p1rem);
            p2Balls.setText(groupLabel(p2g) + " 剩" + p2rem);

            if (score.get("game_over").getAsBoolean()) {
                int winner = score.get("winner").getAsInt();
                String name = winner == 1
                    ? ((MainActivity)getActivity()).getPlayer1Name()
                    : ((MainActivity)getActivity()).getPlayer2Name();
                matchEvents.setText(name + " 获胜！");
            }
        });
    }

    private void handlePocketEvent(JsonObject data) {
        if (getActivity() == null) return;
        String color = data.get("color").getAsString();
        boolean isCue = data.get("is_cue").getAsBoolean();
        getActivity().runOnUiThread(() -> {
            String msg = isCue ? "犯规！白球进袋" : color + "球进袋";
            matchEvents.setText(msg);
        });
    }

    private void updateTurnIndicator(int player) {
        if (player == 1) {
            p1Turn.setVisibility(View.VISIBLE);
            p1Turn.setText("👈 击球中");
            p2Turn.setVisibility(View.GONE);
            p1Score.getParent().requestLayout();
        } else {
            p2Turn.setVisibility(View.VISIBLE);
            p2Turn.setText("👈 击球中");
            p1Turn.setVisibility(View.GONE);
        }
    }

    // ─── New WebSocket handlers ─────────────────────────────

    private void handleShotResult(JsonObject data) {
        if (getActivity() == null) return;
        String feedback = data.get("feedback").getAsString();
        boolean passed = data.get("drill_passed").getAsBoolean();
        int consecutive = data.get("consecutive_successes").getAsInt();
        getActivity().runOnUiThread(() -> {
            shotFeedback.setText(feedback);
            shotFeedback.setVisibility(View.VISIBLE);
            shotFeedback.setBackgroundTintList(
                android.content.res.ColorStateList.valueOf(
                    passed ? 0xFF1b5e20 : 0xFF1a237e));
            String stats = "连续成功: " + consecutive + " 次";
            trainingStats.setText(stats);
        });
    }

    private void handlePlacementResult(JsonObject data) {
        if (getActivity() == null) return;
        boolean allCorrect = data.get("all_correct").getAsBoolean();
        String cueError = data.has("cue_error") ? data.get("cue_error").getAsString() : "";
        String targetError = data.has("target_error") ? data.get("target_error").getAsString() : "";
        getActivity().runOnUiThread(() -> {
            if (allCorrect) {
                placementStatus.setText("摆球正确 ✅");
                placementStatus.setTextColor(0xFF4CAF50);
            } else {
                placementStatus.setText("摆球偏差: 白球" + cueError + " 目标" + targetError);
                placementStatus.setTextColor(0xFFFF9800);
            }
            placementStatus.setVisibility(View.VISIBLE);
        });
    }

    private void handleTableState(JsonObject data) {
        if (getActivity() == null) return;
        try {
            String ballCount = data.has("ball_count") ? data.get("ball_count").getAsString() : "0";
            String detected = data.has("detected") && data.get("detected").getAsBoolean() ? "已检测" : "未检测";
            // Draw simple table overview
            final String info = "桌面: " + detected + " | 球数: " + ballCount;
            getActivity().runOnUiThread(() -> {
                if (matchView.getVisibility() == View.VISIBLE) {
                    // Show ball count in match view
                    matchEvents.setText(matchEvents.getText() + "\n" + info);
                }
            });
        } catch (Exception e) {
            Log.e(TAG, "Table state error", e);
        }
    }

    private void handleDrillInfo(JsonObject data) {
        if (getActivity() == null) return;
        final String desc = data.has("drill") ? data.getAsJsonObject("drill").get("description").getAsString() : "";
        final StringBuilder pos = new StringBuilder();
        if (data.has("drill")) {
            JsonObject drill = data.getAsJsonObject("drill");
            if (drill.has("cue_pos")) {
                var arr = drill.getAsJsonArray("cue_pos");
                pos.append("白球: (").append(arr.get(0).getAsDouble())
                   .append(", ").append(arr.get(1).getAsDouble()).append(")\n");
            }
            if (drill.has("target_pos")) {
                var arr = drill.getAsJsonArray("target_pos");
                pos.append("目标: (").append(arr.get(0).getAsDouble())
                   .append(", ").append(arr.get(1).getAsDouble()).append(")");
            }
            if (drill.has("pocket_pos")) {
                var p = drill.getAsJsonArray("pocket_pos");
                pos.append("\n袋口: (").append(p.get(0).getAsDouble())
                   .append(", ").append(p.get(1).getAsDouble()).append(")");
            }
        }
        final String levelName = data.has("progress") ? data.getAsJsonObject("progress").get("level_name").getAsString() : "";
        final String drillNum = data.has("progress") ? data.getAsJsonObject("progress").get("drill").getAsString() : "0";
        final String totalDrills = data.has("progress") ? data.getAsJsonObject("progress").get("total_drills").getAsString() : "0";
        final String consecStr = data.has("progress") && data.getAsJsonObject("progress").has("consecutive_successes")
            ? data.getAsJsonObject("progress").get("consecutive_successes").getAsString() : "0";
        final String attempts = data.has("progress") && data.getAsJsonObject("progress").has("total_attempts")
            ? data.getAsJsonObject("progress").get("total_attempts").getAsString() : "0";

        getActivity().runOnUiThread(() -> {
            drillDescription.setText(desc);
            drillPositions.setText(pos.toString());
            drillLevel.setText("档位: " + levelName);
            drillProgress.setText("第 " + drillNum + " / " + totalDrills + " 题");
            trainingStats.setText("连续成功: " + consecStr + " | 总尝试: " + attempts);
        });
    }

    private void switchTurn() {
        MainActivity activity = (MainActivity) getActivity();
        if (activity != null) {
            Toast.makeText(activity, "击球权已交换", Toast.LENGTH_SHORT).show();
        }
    }
}
