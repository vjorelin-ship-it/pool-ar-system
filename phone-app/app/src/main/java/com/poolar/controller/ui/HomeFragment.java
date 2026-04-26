package com.poolar.controller.ui;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.LinearLayout;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import com.poolar.controller.MainActivity;
import com.poolar.controller.R;
import com.poolar.controller.network.ApiClient;
import com.poolar.controller.network.ServiceDiscovery;

public class HomeFragment extends Fragment {

    private TextView connectionStatus;
    private View statusDot;
    private EditText manualIp;
    private Button btnConnect, btnStart, btnStop;
    private ApiClient apiClient;
    private String currentHost;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container,
                             Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_home, container, false);
        connectionStatus = v.findViewById(R.id.connection_status);
        statusDot = v.findViewById(R.id.status_dot);
        manualIp = v.findViewById(R.id.manual_ip);
        btnConnect = v.findViewById(R.id.btn_connect);
        btnStart = v.findViewById(R.id.btn_start);
        btnStop = v.findViewById(R.id.btn_stop);

        setButtonsEnabled(false);
        startDiscovery();

        btnConnect.setOnClickListener(view -> {
            String ip = manualIp.getText().toString().trim();
            if (!ip.isEmpty()) connectTo(ip);
            else Toast.makeText(getActivity(), "请输入IP地址", Toast.LENGTH_SHORT).show();
        });

        btnStart.setOnClickListener(view -> {
            if (apiClient != null)
                apiClient.startSystem(callback("系统已启动"));
        });

        btnStop.setOnClickListener(view -> {
            if (apiClient != null)
                apiClient.stopSystem(callback("系统已停止"));
        });

        // Mode cards
        v.findViewById(R.id.card_match).setOnClickListener(view -> {
            showMatchNameDialog();
        });

        v.findViewById(R.id.card_training).setOnClickListener(view -> {
            enterMode("training");
        });

        v.findViewById(R.id.card_challenge).setOnClickListener(view -> {
            enterMode("challenge");
        });

        return v;
    }

    private void startDiscovery() {
        connectionStatus.setText("正在搜索服务器...");
        new ServiceDiscovery().discoverServer(new ServiceDiscovery.DiscoveryCallback() {
            @Override
            public void onFound(String host, int port) {
                connectTo(host);
            }

            @Override
            public void onError(String message) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        connectionStatus.setText("自动发现失败，请手动输入IP");
                        connectionStatus.setTextColor(0xFFF44336);
                    });
                }
            }
        });
    }

    private void connectTo(String host) {
        currentHost = host;
        apiClient = new ApiClient(host);
        if (getActivity() != null) {
            // Persist server IP
            getActivity().getSharedPreferences("prefs", 0)
                .edit().putString("server_ip", host).apply();
            getActivity().runOnUiThread(() -> {
                connectionStatus.setText("已连接: " + host);
                connectionStatus.setTextColor(0xFF4CAF50);
                statusDot.setBackgroundResource(android.R.drawable.presence_online);
                manualIp.setText(host);
                setButtonsEnabled(true);
            });
        }
    }

    private void enterMode(String mode) {
        MainActivity activity = (MainActivity) getActivity();
        if (activity == null) return;
        activity.setCurrentMode(mode);
        if (apiClient != null) {
            apiClient.setMode(mode, new ApiClient.ApiCallback<Object>() {
                @Override public void onResult(Object result) {}
                @Override public void onError(String error) {
                    showToast("切换模式失败: " + error);
                }
            });
        }
        activity.switchTab(R.id.nav_active);
    }

    private void showMatchNameDialog() {
        MainActivity activity = (MainActivity) getActivity();
        if (activity == null) return;

        android.app.AlertDialog.Builder builder = new android.app.AlertDialog.Builder(getContext());
        builder.setTitle("比赛选手");

        LinearLayout layout = new LinearLayout(getContext());
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(40, 20, 40, 20);

        TextView label1 = new TextView(getContext());
        label1.setText("选手一");
        label1.setTextColor(0xFF888888);
        layout.addView(label1);

        EditText input1 = new EditText(getContext());
        input1.setText(activity.getPlayer1Name());
        input1.setHint("选手一姓名");
        layout.addView(input1);

        TextView spacer = new TextView(getContext());
        spacer.setText("");
        spacer.setPadding(0, 10, 0, 10);
        layout.addView(spacer);

        TextView label2 = new TextView(getContext());
        label2.setText("选手二");
        label2.setTextColor(0xFF888888);
        layout.addView(label2);

        EditText input2 = new EditText(getContext());
        input2.setText(activity.getPlayer2Name());
        input2.setHint("选手二姓名");
        layout.addView(input2);

        builder.setView(layout);

        builder.setPositiveButton("开始比赛", (dialog, which) -> {
            String p1 = input1.getText().toString().trim();
            String p2 = input2.getText().toString().trim();
            if (p1.isEmpty()) p1 = "选手一";
            if (p2.isEmpty()) p2 = "选手二";
            activity.setPlayerNames(p1, p2);

            // Start match via API
            if (apiClient != null) {
                apiClient.setMode("match", new ApiClient.ApiCallback<Object>() {
                    @Override
                    public void onResult(Object result) {}
                    @Override
                    public void onError(String error) {}
                });
            }
            activity.setCurrentMode("match");
            activity.switchTab(R.id.nav_active);
        });

        builder.setNegativeButton("取消", null);
        builder.show();
    }

    private void setButtonsEnabled(boolean enabled) {
        btnStart.setEnabled(enabled);
        btnStop.setEnabled(enabled);
    }

    private ApiClient.ApiCallback<Void> callback(String msg) {
        return new ApiClient.ApiCallback<Void>() {
            @Override
            public void onResult(Void result) {
                showToast(msg);
            }

            @Override
            public void onError(String error) {
                showToast("失败: " + error);
            }
        };
    }

    private void showToast(String msg) {
        if (getActivity() != null)
            getActivity().runOnUiThread(() ->
                Toast.makeText(getActivity(), msg, Toast.LENGTH_SHORT).show());
    }
}
