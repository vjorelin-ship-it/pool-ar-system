package com.poolar.controller;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import androidx.fragment.app.Fragment;
import com.poolar.controller.network.ApiClient;

public class InProgressFragment extends Fragment {
    private TextView modeText, infoText;
    private Handler handler = new Handler(Looper.getMainLooper());
    private Runnable refresher;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_progress, container, false);
        modeText = v.findViewById(R.id.modeText);
        infoText = v.findViewById(R.id.infoText);

        refresher = new Runnable() {
            @Override public void run() {
                ApiClient.getStatus(data -> {
                    if (data != null) {
                        String mode = data.optString("mode", "idle");
                        modeText.setText("当前模式: " + mode);
                        if ("match".equals(mode)) {
                            ApiClient.getScore(scoreData -> {
                                if (scoreData != null) {
                                    infoText.setText("选手一: " + scoreData.optInt("player1_score", 0)
                                        + "  |  选手二: " + scoreData.optInt("player2_score", 0));
                                }
                            });
                        } else if ("training".equals(mode) || "challenge".equals(mode)) {
                            infoText.setText("等待训练题选择...");
                        } else {
                            infoText.setText("系统空闲中");
                        }
                    }
                });
                handler.postDelayed(this, 3000);
            }
        };
        handler.post(refresher);
        return v;
    }

    @Override public void onDestroyView() {
        super.onDestroyView();
        handler.removeCallbacks(refresher);
    }
}
