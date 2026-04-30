package com.poolar.controller;

import android.app.AlertDialog;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.google.gson.JsonObject;
import com.poolar.controller.network.ApiClient;

public class InProgressFragment extends Fragment {
    private View matchView, trainingView;
    private String activeMode = "idle";

    // 比赛模式 View 引用
    private TextView p1Name, p1Score, p1Group, p1Indicator;
    private TextView p2Name, p2Score, p2Group, p2Indicator;
    private LinearLayout solidsRow, stripesRow;
    private TextView ball8, ballsRemaining;
    private Button btnSwitchTurn;
    private boolean[] pocketedBalls = new boolean[16]; // index 1-15

    // 训练模式 View 引用
    private TextView levelNameText, drillProgressText, cuePosText, targetPosText;
    private TextView pocketPosText, techniqueText, placementStatusText;
    private TextView cueTypeText, powerText, cueLandingText;
    private TextView shotResultText, shotFeedbackText;
    private TextView consecutiveText, bestRecordText, totalProgressText;
    private View progressBar;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_progress, container, false);

        // 预加载两个子View
        matchView = inflater.inflate(R.layout.view_match, (ViewGroup) v, false);
        trainingView = inflater.inflate(R.layout.view_training, (ViewGroup) v, false);

        // 比赛View绑定
        bindMatchViews(matchView);
        // 训练View绑定
        bindTrainingViews(trainingView);

        // 初始显示匹配当前模式
        String currentMode = ((MainActivity) requireActivity()).currentMode();
        updateMode(currentMode);

        return v;
    }

    private void bindMatchViews(View v) {
        p1Name = v.findViewById(R.id.player1Name);
        p1Score = v.findViewById(R.id.player1Score);
        p1Group = v.findViewById(R.id.player1Group);
        p1Indicator = v.findViewById(R.id.player1Indicator);
        p2Name = v.findViewById(R.id.player2Name);
        p2Score = v.findViewById(R.id.player2Score);
        p2Group = v.findViewById(R.id.player2Group);
        p2Indicator = v.findViewById(R.id.player2Indicator);
        solidsRow = v.findViewById(R.id.solidsRow);
        stripesRow = v.findViewById(R.id.stripesRow);
        ball8 = v.findViewById(R.id.ball8);
        ballsRemaining = v.findViewById(R.id.ballsRemaining);
        btnSwitchTurn = v.findViewById(R.id.btnSwitchTurn);

        btnSwitchTurn.setOnClickListener(v2 -> {
            new AlertDialog.Builder(getContext())
                .setTitle("确认交换击球")
                .setMessage("确定要手动交换击球权吗？")
                .setPositiveButton("确定", (d, w) -> {
                    ApiClient.post("/api/match/switch-turn", null, ok ->
                        Toast.makeText(getContext(), ok ? "已交换" : "失败", Toast.LENGTH_SHORT).show());
                })
                .setNegativeButton("取消", null)
                .show();
        });

        // 初始化球号显示
        initBallGrid();
    }

    private void bindTrainingViews(View v) {
        levelNameText = v.findViewById(R.id.levelNameText);
        drillProgressText = v.findViewById(R.id.drillProgressText);
        cuePosText = v.findViewById(R.id.cuePosText);
        targetPosText = v.findViewById(R.id.targetPosText);
        pocketPosText = v.findViewById(R.id.pocketPosText);
        techniqueText = v.findViewById(R.id.techniqueText);
        placementStatusText = v.findViewById(R.id.placementStatusText);
        cueTypeText = v.findViewById(R.id.cueTypeText);
        powerText = v.findViewById(R.id.powerText);
        cueLandingText = v.findViewById(R.id.cueLandingText);
        shotResultText = v.findViewById(R.id.shotResultText);
        shotFeedbackText = v.findViewById(R.id.shotFeedbackText);
        consecutiveText = v.findViewById(R.id.consecutiveText);
        bestRecordText = v.findViewById(R.id.bestRecordText);
        totalProgressText = v.findViewById(R.id.totalProgressText);
        progressBar = v.findViewById(R.id.progressBar);

        // 返回选关按钮
        v.findViewById(R.id.btnBackToLevels).setOnClickListener(v2 -> {
            BottomNavigationView nav = requireActivity().findViewById(R.id.bottomNav);
            nav.setSelectedItemId(R.id.nav_home);
        });
    }

    private void initBallGrid() {
        solidsRow.removeAllViews();
        stripesRow.removeAllViews();

        for (int i = 1; i <= 7; i++) {
            TextView tv = makeBallView(i);
            solidsRow.addView(tv);
        }
        for (int i = 9; i <= 15; i++) {
            TextView tv = makeBallView(i);
            stripesRow.addView(tv);
        }
    }

    private TextView makeBallView(int number) {
        TextView tv = new TextView(getContext());
        int size = 40;
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(size, size);
        params.setMargins(4, 0, 4, 0);
        tv.setLayoutParams(params);
        tv.setGravity(android.view.Gravity.CENTER);
        tv.setText(getBallUnicode(number));
        tv.setTextColor(getResources().getColor(R.color.text_primary));
        tv.setTextSize(14);
        tv.setBackgroundResource(R.drawable.circle_gray);
        tv.setTag(number);
        return tv;
    }

    private String getBallUnicode(int n) {
        return String.valueOf(Character.toChars(0x245F + n)); // ① = U+2460
    }

    private void updateBallDisplay() {
        for (int i = 1; i <= 15; i++) {
            TextView tv = findBallView(i);
            if (tv != null) {
                if (pocketedBalls[i]) {
                    tv.setTextColor(getResources().getColor(R.color.text_dim));
                    tv.setPaintFlags(tv.getPaintFlags() | android.graphics.Paint.STRIKE_THRU_TEXT_FLAG);
                } else {
                    tv.setTextColor(getResources().getColor(R.color.text_primary));
                    tv.setPaintFlags(tv.getPaintFlags() & ~android.graphics.Paint.STRIKE_THRU_TEXT_FLAG);
                }
            }
        }
    }

    private TextView findBallView(int number) {
        ViewGroup parent = number <= 7 ? solidsRow : (number == 8 ? null : stripesRow);
        if (parent == null) return ball8;
        for (int i = 0; i < parent.getChildCount(); i++) {
            View child = parent.getChildAt(i);
            if (child instanceof TextView && Integer.valueOf(number).equals(child.getTag())) {
                return (TextView) child;
            }
        }
        return null;
    }

    public void updateMode(String mode) {
        activeMode = mode;
        ViewGroup container = requireView().findViewById(R.id.progressContainer);
        container.removeAllViews();

        if ("match".equals(mode)) {
            container.addView(matchView);
        } else if ("training".equals(mode) || "challenge".equals(mode)) {
            container.addView(trainingView);
        } else {
            TextView placeholder = new TextView(getContext());
            placeholder.setText("请在主页选择一个模式开始");
            placeholder.setTextColor(getResources().getColor(R.color.text_secondary));
            placeholder.setTextSize(16);
            placeholder.setGravity(android.view.Gravity.CENTER);
            placeholder.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
            container.addView(placeholder);
        }
    }

    // WebSocket 消息入口
    public void onWebSocketMessage(String type, JsonObject data) {
        if (!isAdded()) return;

        switch (type) {
            case "score_update":
                handleScoreUpdate(data);
                break;
            case "pocket_event":
                handlePocketEvent(data);
                break;
            case "drill_info":
                handleDrillInfo(data);
                break;
            case "placement_result":
                handlePlacementResult(data);
                break;
            case "shot_result":
                handleShotResult(data);
                break;
            case "table_state":
                handleTableState(data);
                break;
        }
    }

    private void handleScoreUpdate(JsonObject data) {
        if (p1Score != null && data.has("player1_score")) {
            p1Score.setText(String.valueOf(data.get("player1_score").getAsInt()));
        }
        if (p2Score != null && data.has("player2_score")) {
            p2Score.setText(String.valueOf(data.get("player2_score").getAsInt()));
        }
        if (data.has("current_player")) {
            int cp = data.get("current_player").getAsInt();
            if (cp == 1) {
                p1Indicator.setVisibility(View.VISIBLE);
                p2Indicator.setVisibility(View.GONE);
            } else {
                p2Indicator.setVisibility(View.VISIBLE);
                p1Indicator.setVisibility(View.GONE);
            }
        }
        if (data.has("player1_group") && p1Group != null) {
            p1Group.setText(data.get("player1_group").getAsString());
        }
        if (data.has("player2_group") && p2Group != null) {
            p2Group.setText(data.get("player2_group").getAsString());
        }
        if (data.has("game_over") && data.get("game_over").getAsBoolean()) {
            int winner = data.has("winner") ? data.get("winner").getAsInt() : 0;
            String winMsg = (winner == 1 ? p1Name.getText() : p2Name.getText()) + " 获胜！";
            Toast.makeText(getContext(), winMsg, Toast.LENGTH_LONG).show();
        }
    }

    private void handlePocketEvent(JsonObject data) {
        int ballNumber = data.has("ball_number") ? data.get("ball_number").getAsInt() : 0;
        if (ballNumber >= 1 && ballNumber <= 15) {
            pocketedBalls[ballNumber] = true;
            updateBallDisplay();
        }
        updateBallsRemaining();
    }

    private void updateBallsRemaining() {
        int solidsRemaining = 0, stripesRemaining = 0;
        for (int i = 1; i <= 7; i++) if (!pocketedBalls[i]) solidsRemaining++;
        for (int i = 9; i <= 15; i++) if (!pocketedBalls[i]) stripesRemaining++;
        String status = "纯色剩" + solidsRemaining + "颗  花色剩" + stripesRemaining + "颗  黑8" +
            (pocketedBalls[8] ? "已进" : "在台");
        if (ballsRemaining != null) ballsRemaining.setText(status);
    }

    private void handleDrillInfo(JsonObject data) {
        if (levelNameText != null && data.has("level_name")) {
            levelNameText.setText(data.get("level_name").getAsString());
        }
        if (drillProgressText != null && data.has("drill") && data.has("total_drills")) {
            drillProgressText.setText("第 " + data.get("drill").getAsString() +
                " 题 / 共 " + data.get("total_drills").getAsString() + " 题");
        }
        if (cuePosText != null && data.has("cue_pos")) {
            cuePosText.setText("● 白球: " + data.get("cue_pos").getAsString());
        }
        if (targetPosText != null && data.has("target_pos")) {
            targetPosText.setText("○ 目标球: " + data.get("target_pos").getAsString());
        }
        if (pocketPosText != null && data.has("pocket_pos")) {
            pocketPosText.setText("◎ 目标袋: " + data.get("pocket_pos").getAsString());
        }
        if (techniqueText != null && data.has("description")) {
            techniqueText.setText("📝 " + data.get("description").getAsString());
        }
    }

    private void handlePlacementResult(JsonObject data) {
        if (placementStatusText == null) return;
        boolean allCorrect = data.has("all_correct") && data.get("all_correct").getAsBoolean();
        if (allCorrect) {
            placementStatusText.setText("✅ 摆球正确");
            placementStatusText.setTextColor(getResources().getColor(R.color.success));
        } else {
            placementStatusText.setText("❌ 摆球位置有偏差，请调整");
            placementStatusText.setTextColor(getResources().getColor(R.color.error));
        }
    }

    private void handleShotResult(JsonObject data) {
        if (shotResultText == null) return;
        boolean success = data.has("success") && data.get("success").getAsBoolean();
        if (success) {
            shotResultText.setText("✅ 目标球进袋！");
            shotResultText.setTextColor(getResources().getColor(R.color.success));
        } else {
            shotResultText.setText("❌ 未成功");
            shotResultText.setTextColor(getResources().getColor(R.color.error));
        }
        if (shotFeedbackText != null && data.has("feedback")) {
            shotFeedbackText.setText(data.get("feedback").getAsString());
            shotFeedbackText.setVisibility(View.VISIBLE);
        }
        if (consecutiveText != null && data.has("consecutive")) {
            consecutiveText.setText("🔥 连续成功 " + data.get("consecutive").getAsInt() + " 次");
        }
    }

    private void handleTableState(JsonObject data) {
        if (data.has("mode")) {
            String mode = data.get("mode").getAsString();
            if (!mode.equals(activeMode)) {
                updateMode(mode);
            }
        }
    }

    // 重连后刷新状态
    public void refreshState() {
        if (!isAdded()) return;
        ApiClient.getStatus(data -> {
            if (data != null && isAdded()) {
                String mode = data.optString("mode", "idle");
                if (!mode.equals(activeMode)) {
                    getActivity().runOnUiThread(() -> updateMode(mode));
                }
                if ("match".equals(mode)) {
                    ApiClient.getScore(scoreData -> {
                        if (scoreData != null && isAdded() && p1Score != null) {
                            getActivity().runOnUiThread(() -> {
                                p1Score.setText(String.valueOf(scoreData.optInt("player1_score", 0)));
                                p2Score.setText(String.valueOf(scoreData.optInt("player2_score", 0)));
                            });
                        }
                    });
                }
            }
        });
    }

    @Override
    public void onDestroyView() {
        super.onDestroyView();
    }
}
