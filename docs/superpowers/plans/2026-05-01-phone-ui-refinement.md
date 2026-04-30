# 手机APP UI精炼实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将手机APP从现有三Tab骨架升级为完整的极简竞技风格界面，包含WebSocket实时通信、比赛进行中界面、训练进行中界面、以及统一的设计系统。

**Architecture:** MainActivity持有WebSocketClient实例，三个Fragment通过回调接口接收实时消息。Tab 2 (InProgressFragment) 根据当前模式(match/training/challenge)动态切换内部View。所有颜色/字体/间距统一引用 colors.xml / styles.xml。

**Tech Stack:** Java 17, Android SDK 34, Material Components, Java-WebSocket 1.5.4, Gson 2.10.1

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `res/values/colors.xml` | 新建 | 极简竞技配色Token |
| `res/values/strings.xml` | 新建 | 中文字符串资源 |
| `res/values/styles.xml` | 重写 | 主题+组件样式 |
| `res/drawable/btn_primary_bg.xml` | 新建 | 金色实心按钮背景(2px圆角) |
| `res/drawable/btn_secondary_bg.xml` | 新建 | 透明边框按钮背景 |
| `res/drawable/card_bg.xml` | 新建 | 卡片背景(#0D0D0D + 2px圆角) |
| `res/drawable/divider_gold.xml` | 新建 | 金色渐变分割线 |
| `res/drawable/badge_accent.xml` | 新建 | 左侧金色强调条(3px宽) |
| `res/layout/activity_main.xml` | 修改 | 套用新背景色+导航栏配色 |
| `res/layout/fragment_home.xml` | 重写 | 主页布局 |
| `res/layout/fragment_progress.xml` | 重写 | 进行中容器(FrameLayout占位) |
| `res/layout/fragment_settings.xml` | 重写 | 设置布局 |
| `res/layout/view_match.xml` | 新建 | 比赛进行中内容 |
| `res/layout/view_training.xml` | 新建 | 训练进行中内容 |
| `res/layout/dialog_player_names.xml` | 新建 | 比赛选手姓名对话框 |
| `res/layout/dialog_level_select.xml` | 新建 | 训练关卡选择对话框 |
| `java/.../WebSocketClient.java` | 新建 | WebSocket连接+消息分发 |
| `java/.../MainActivity.java` | 修改 | 集成WebSocket, Fragment复用, 共享状态 |
| `java/.../HomeFragment.java` | 重写 | 新样式+对话框模式切换 |
| `java/.../InProgressFragment.java` | 重写 | 模式切换MatchView/TrainingView |
| `java/.../SettingsFragment.java` | 重写 | 新样式+预览开关+默认选手 |

---

### Task 1: 资源文件 — colors.xml + strings.xml + drawables

**Files:**
- Create: `phone-app/app/src/main/res/values/colors.xml`
- Create: `phone-app/app/src/main/res/values/strings.xml`
- Create: `phone-app/app/src/main/res/drawable/btn_primary_bg.xml`
- Create: `phone-app/app/src/main/res/drawable/btn_secondary_bg.xml`
- Create: `phone-app/app/src/main/res/drawable/card_bg.xml`
- Create: `phone-app/app/src/main/res/drawable/divider_gold.xml`
- Create: `phone-app/app/src/main/res/drawable/badge_accent.xml`

- [ ] **Step 1: 创建 colors.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- 背景 -->
    <color name="bg_primary">#FF080808</color>
    <color name="bg_card">#FF0D0D0D</color>
    <color name="bg_surface">#FF111111</color>

    <!-- 强调色 -->
    <color name="accent">#FFFFC107</color>
    <color name="accent_dim">#FFC8A000</color>
    <color name="accent_light">#FFFFE082</color>

    <!-- 边框 -->
    <color name="border_subtle">#FF1A1A1A</color>
    <color name="border_medium">#FF222222</color>
    <color name="border_strong">#FF2A2A2A</color>

    <!-- 文字 -->
    <color name="text_primary">#FFFFFFFF</color>
    <color name="text_secondary">#FF888888</color>
    <color name="text_tertiary">#FF666666</color>
    <color name="text_dim">#FF555555</color>

    <!-- 语义色 -->
    <color name="error">#FFFF1744</color>
    <color name="success">#FF00E676</color>
</resources>
```

- [ ] **Step 2: 创建 strings.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_title">POOL·AR</string>
    <string name="tab_home">主页</string>
    <string name="tab_progress">进行中</string>
    <string name="tab_settings">设置</string>

    <string name="btn_start">▶ 启动系统</string>
    <string name="btn_stop">■ 停止系统</string>
    <string name="btn_switch_turn">🔄 交换击球</string>

    <string name="label_mode_select">模式选择</string>
    <string name="label_system_info">系统信息</string>
    <string name="label_server">服务器</string>
    <string name="label_preview">预览</string>
    <string name="label_calibration">校准</string>
    <string name="label_model">模型</string>
    <string name="label_default_players">默认选手</string>

    <string name="card_match_title">🏆 比赛模式</string>
    <string name="card_match_desc">双人轮流击球，自动计分</string>
    <string name="card_training_title">🎯 训练模式</string>
    <string name="card_training_desc">10档难度，50道标准训练题</string>
    <string name="card_challenge_title">⭐ 闯关模式</string>
    <string name="card_challenge_desc">连续成功3次晋级下一关</string>

    <string name="match_in_progress">🏆 比赛进行中</string>
    <string name="training_in_progress">训练进行中</string>
    <string name="label_ball_status">球状态</string>
    <string name="label_drill_progress">训练进度</string>
    <string name="label_placement">摆球要求</string>
    <string name="label_placement_verify">摆球验证</string>
    <string name="label_shot_recommend">推荐击球</string>
    <string name="label_shot_result">击球结果</string>
    <string name="label_challenge_progress">闯关进度</string>

    <string name="status_connected">⚡ 已连接</string>
    <string name="status_disconnected">已断开</string>

    <string name="dialog_match_title">🏆 比赛选手</string>
    <string name="hint_player1">选手一</string>
    <string name="hint_player2">选手二</string>
    <string name="save_as_default">保存为默认</string>
    <string name="btn_start_match">开始比赛</string>

    <string name="dialog_level_title">选择训练关卡</string>
</resources>
```

- [ ] **Step 3: 创建 drawable 资源文件**

**btn_primary_bg.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/accent"/>
    <corners android:radius="2dp"/>
</shape>
```

**btn_secondary_bg.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@android:color/transparent"/>
    <stroke android:width="1dp" android:color="@color/border_strong"/>
    <corners android:radius="2dp"/>
</shape>
```

**card_bg.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/bg_card"/>
    <stroke android:width="1dp" android:color="@color/border_subtle"/>
    <corners android:radius="2dp"/>
</shape>
```

**divider_gold.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <gradient
        android:startColor="@color/accent_dim"
        android:centerColor="@color/accent"
        android:endColor="@color/accent_dim"
        android:type="linear"/>
    <size android:height="1dp"/>
</shape>
```

**badge_accent.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/accent"/>
    <corners android:radius="0dp"/>
</shape>
```

- [ ] **Step 4: 验证 — 检查XML文件语法正确**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit**

```bash
git add phone-app/app/src/main/res/values/colors.xml \
        phone-app/app/src/main/res/values/strings.xml \
        phone-app/app/src/main/res/drawable/btn_primary_bg.xml \
        phone-app/app/src/main/res/drawable/btn_secondary_bg.xml \
        phone-app/app/src/main/res/drawable/card_bg.xml \
        phone-app/app/src/main/res/drawable/divider_gold.xml \
        phone-app/app/src/main/res/drawable/badge_accent.xml
git commit -m "feat: add design tokens — colors, strings, drawable shapes for 极简竞技 theme"
```

---

### Task 2: styles.xml 重写

**Files:**
- Modify: `phone-app/app/src/main/res/values/styles.xml`

- [ ] **Step 1: 重写 styles.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.PoolAR" parent="Theme.MaterialComponents.DayNight.NoActionBar">
        <item name="colorPrimary">@color/accent</item>
        <item name="colorPrimaryVariant">@color/accent_dim</item>
        <item name="colorOnPrimary">@color/bg_primary</item>
        <item name="colorSecondary">@color/accent</item>
        <item name="android:statusBarColor">@color/bg_primary</item>
        <item name="android:navigationBarColor">@color/bg_primary</item>
        <item name="android:windowBackground">@color/bg_primary</item>
    </style>

    <!-- 卡片基础 -->
    <style name="CardBase">
        <item name="android:background">@drawable/card_bg</item>
        <item name="android:padding">16dp</item>
        <item name="android:layout_marginBottom">12dp</item>
    </style>

    <!-- 主按钮（金色实心+黑字） -->
    <style name="ButtonPrimary" parent="Widget.MaterialComponents.Button">
        <item name="android:background">@drawable/btn_primary_bg</item>
        <item name="android:textColor">@color/bg_primary</item>
        <item name="android:textSize">16sp</item>
        <item name="android:fontFamily">sans-serif-medium</item>
        <item name="android:padding">14dp</item>
        <item name="android:minHeight">52dp</item>
        <item name="android:gravity">center</item>
    </style>

    <!-- 次按钮（透明+灰边框） -->
    <style name="ButtonSecondary" parent="Widget.MaterialComponents.Button">
        <item name="android:background">@drawable/btn_secondary_bg</item>
        <item name="android:textColor">@color/text_secondary</item>
        <item name="android:textSize">14sp</item>
        <item name="android:padding">12dp</item>
        <item name="android:minHeight">44dp</item>
        <item name="android:gravity">center</item>
    </style>

    <!-- 模式选择卡片 -->
    <style name="ModeCard">
        <item name="android:padding">16dp</item>
        <item name="android:layout_marginBottom">8dp</item>
        <item name="android:minHeight">60dp</item>
    </style>

    <!-- 大字比分 -->
    <style name="ScoreNumber">
        <item name="android:textColor">@color/text_primary</item>
        <item name="android:textSize">48sp</item>
        <item name="android:fontFamily">monospace</item>
        <item name="android:textStyle">bold</item>
        <item name="android:gravity">center</item>
    </style>

    <!-- 标签文字 -->
    <style name="Label">
        <item name="android:textColor">@color/text_tertiary</item>
        <item name="android:textSize">11sp</item>
        <item name="android:letterSpacing">0.08</item>
        <item name="android:fontFamily">sans-serif-medium</item>
        <item name="android:textAllCaps">true</item>
        <item name="android:layout_marginTop">16dp</item>
        <item name="android:layout_marginBottom">8dp</item>
    </style>

    <!-- 正文 -->
    <style name="BodyText">
        <item name="android:textColor">@color/text_primary</item>
        <item name="android:textSize">15sp</item>
        <item name="android:lineSpacingExtra">4dp</item>
    </style>

    <!-- 次级文字 -->
    <style name="BodySecondary">
        <item name="android:textColor">@color/text_secondary</item>
        <item name="android:textSize">13sp</item>
    </style>

    <!-- 输入框样式 -->
    <style name="InputDark" parent="Widget.MaterialComponents.TextInputLayout.OutlinedBox">
        <item name="boxStrokeColor">@color/border_medium</item>
        <item name="hintTextColor">@color/text_tertiary</item>
        <item name="android:textColor">@color/text_primary</item>
        <item name="android:textColorHint">@color/text_dim</item>
        <item name="boxBackgroundColor">@color/bg_surface</item>
    </style>
</resources>
```

- [ ] **Step 2: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Commit**

```bash
git add phone-app/app/src/main/res/values/styles.xml
git commit -m "feat: rewrite styles.xml with 极简竞技 theme — amber accent, card/button/text styles"
```

---

### Task 3: WebSocketClient.java

**Files:**
- Create: `phone-app/app/src/main/java/com/poolar/controller/network/WebSocketClient.java`

**职责:** WebSocket连接管理，消息JSON解析，回调分发。采用观察者模式。

- [ ] **Step 1: 创建 WebSocketClient.java**

```java
package com.poolar.controller.network;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import java.net.URI;
import java.util.concurrent.CopyOnWriteArrayList;

public class WebSocketClient {
    private static final String TAG = "PoolAR-WS";
    private final Gson gson = new Gson();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final CopyOnWriteArrayList<MessageListener> listeners = new CopyOnWriteArrayList<>();
    private org.java_websocket.client.WebSocketClient ws;
    private String host;
    private int port;
    private String path;
    private boolean shouldReconnect = true;

    public interface MessageListener {
        void onMessage(String type, JsonObject data);
        default void onConnected() {}
        default void onDisconnected() {}
    }

    public WebSocketClient() {}

    public void connect(String host, int port, String path) {
        this.host = host;
        this.port = port;
        this.path = path;
        this.shouldReconnect = true;
        doConnect();
    }

    private void doConnect() {
        String url = "ws://" + host + ":" + port + path;
        try {
            ws = new org.java_websocket.client.WebSocketClient(new URI(url)) {
                @Override
                public void onOpen(org.java_websocket.handshake.ServerHandshake handshake) {
                    Log.d(TAG, "Connected to " + url);
                    mainHandler.post(() -> {
                        for (MessageListener l : listeners) l.onConnected();
                    });
                }

                @Override
                public void onMessage(String message) {
                    try {
                        JsonObject json = gson.fromJson(message, JsonObject.class);
                        String type = json.has("type") ? json.get("type").getAsString() : "";
                        JsonObject data = json.has("data") ? json.getAsJsonObject("data") : new JsonObject();
                        mainHandler.post(() -> {
                            for (MessageListener l : listeners) l.onMessage(type, data);
                        });
                    } catch (Exception e) {
                        Log.e(TAG, "Parse error", e);
                    }
                }

                @Override
                public void onClose(int code, String reason, boolean remote) {
                    Log.d(TAG, "Disconnected: " + reason);
                    mainHandler.post(() -> {
                        for (MessageListener l : listeners) l.onDisconnected();
                    });
                    if (shouldReconnect) {
                        mainHandler.postDelayed(this::doConnect, 3000);
                    }
                }

                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "WS error", ex);
                }
            };
            ws.connect();
        } catch (Exception e) {
            Log.e(TAG, "Connect failed", e);
            if (shouldReconnect) {
                mainHandler.postDelayed(this::doConnect, 3000);
            }
        }
    }

    public void addListener(MessageListener listener) {
        listeners.add(listener);
    }

    public void removeListener(MessageListener listener) {
        listeners.remove(listener);
    }

    public void send(JsonObject msg) {
        if (ws != null && ws.isOpen()) {
            try {
                ws.send(gson.toJson(msg));
            } catch (Exception e) {
                Log.e(TAG, "Send error", e);
            }
        }
    }

    public void disconnect() {
        shouldReconnect = false;
        if (ws != null) {
            try { ws.close(); } catch (Exception e) {}
        }
    }

    public boolean isConnected() {
        return ws != null && ws.isOpen();
    }
}
```

- [ ] **Step 2: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Commit**

```bash
git add phone-app/app/src/main/java/com/poolar/controller/network/WebSocketClient.java
git commit -m "feat: add WebSocketClient with observer pattern for real-time server push"
```

---

### Task 4: activity_main.xml + MainActivity.java 修改

**Files:**
- Modify: `phone-app/app/src/main/res/layout/activity_main.xml`
- Modify: `phone-app/app/src/main/java/com/poolar/controller/MainActivity.java`

- [ ] **Step 1: 修改 activity_main.xml 配色**

将 activity_main.xml 中的底部导航栏颜色从 `#1a1f2b` / `#00e5a0` 改为新设计：

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:background="@color/bg_primary">
    <FrameLayout
        android:id="@+id/fragmentContainer"
        android:layout_width="match_parent"
        android:layout_height="0dp"
        android:layout_weight="1"/>
    <com.google.android.material.bottomnavigation.BottomNavigationView
        android:id="@+id/bottomNav"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:background="@color/bg_card"
        app:itemIconTint="@color/accent"
        app:itemTextColor="@color/text_secondary"
        app:menu="@menu/bottom_nav"/>
</LinearLayout>
```

- [ ] **Step 2: 修改 MainActivity.java — 集成 WebSocket + Fragment 复用 + 共享状态**

```java
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
    }

    @Override
    public void onDisconnected() {
        if (homeFragment != null) homeFragment.onWsDisconnected();
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
```

- [ ] **Step 3: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: 编译失败 — HomeFragment/InProgressFragment/SettingsFragment 缺少新方法 (onWebSocketMessage, onWsConnected 等)。这是预期的，后续Task会补充。

- [ ] **Step 4: Commit**

```bash
git add phone-app/app/src/main/res/layout/activity_main.xml \
        phone-app/app/src/main/java/com/poolar/controller/MainActivity.java
git commit -m "feat: integrate WebSocketClient into MainActivity with fragment caching and shared state"
```

---

### Task 5: HomeFragment 重写

**Files:**
- Modify: `phone-app/app/src/main/res/layout/fragment_home.xml`
- Modify: `phone-app/app/src/main/java/com/poolar/controller/HomeFragment.java`
- Create: `phone-app/app/src/main/res/layout/dialog_player_names.xml`
- Create: `phone-app/app/src/main/res/layout/dialog_level_select.xml`

- [ ] **Step 1: 重写 fragment_home.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<ScrollView xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/bg_primary"
    android:padding="16dp">
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical">

        <!-- 顶栏：标题 + 连接状态 -->
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="horizontal"
            android:gravity="center_vertical"
            android:layout_marginBottom="20dp">
            <TextView
                android:layout_width="0dp"
                android:layout_height="wrap_content"
                android:layout_weight="1"
                android:text="@string/app_title"
                android:textColor="@color/text_primary"
                android:textSize="22sp"
                android:fontFamily="sans-serif-medium"/>
            <TextView
                android:id="@+id/connectionStatus"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/status_disconnected"
                android:textColor="@color/text_tertiary"
                android:textSize="12sp"/>
        </LinearLayout>

        <!-- 启动/停止按钮 -->
        <Button
            android:id="@+id/btnStart"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            style="@style/ButtonPrimary"
            android:text="@string/btn_start"/>
        <Button
            android:id="@+id/btnStop"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            style="@style/ButtonSecondary"
            android:text="@string/btn_stop"/>

        <!-- 分隔线 -->
        <View
            android:layout_width="match_parent"
            android:layout_height="1dp"
            android:layout_marginTop="20dp"
            android:layout_marginBottom="8dp"
            android:background="@color/border_medium"/>

        <TextView
            style="@style/Label"
            android:text="@string/label_mode_select"/>

        <!-- 模式卡片 — LinearLayout可点击, 两行文字 -->
        <LinearLayout android:id="@+id/cardMatch"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            style="@style/ModeCard"
            android:orientation="vertical"
            android:clickable="true"
            android:focusable="true"
            android:background="@drawable/card_bg">
            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/card_match_title"
                android:textColor="@color/text_primary"
                android:textSize="16sp"
                android:fontFamily="sans-serif-medium"/>
            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/card_match_desc"
                android:textColor="@color/text_secondary"
                android:textSize="13sp"
                android:layout_marginTop="4dp"/>
        </LinearLayout>
        <LinearLayout android:id="@+id/cardTraining"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            style="@style/ModeCard"
            android:orientation="vertical"
            android:clickable="true"
            android:focusable="true"
            android:background="@drawable/card_bg">
            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/card_training_title"
                android:textColor="@color/text_primary"
                android:textSize="16sp"
                android:fontFamily="sans-serif-medium"/>
            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/card_training_desc"
                android:textColor="@color/text_secondary"
                android:textSize="13sp"
                android:layout_marginTop="4dp"/>
        </LinearLayout>
        <LinearLayout android:id="@+id/cardChallenge"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            style="@style/ModeCard"
            android:orientation="vertical"
            android:clickable="true"
            android:focusable="true"
            android:background="@drawable/card_bg">
            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/card_challenge_title"
                android:textColor="@color/text_primary"
                android:textSize="16sp"
                android:fontFamily="sans-serif-medium"/>
            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/card_challenge_desc"
                android:textColor="@color/text_secondary"
                android:textSize="13sp"
                android:layout_marginTop="4dp"/>
        </LinearLayout>

        <!-- 分隔线 -->
        <View
            android:layout_width="match_parent"
            android:layout_height="1dp"
            android:layout_marginTop="16dp"
            android:layout_marginBottom="8dp"
            android:background="@color/border_medium"/>

        <TextView
            style="@style/Label"
            android:text="@string/label_system_info"/>

        <!-- 系统信息卡片 -->
        <LinearLayout
            android:id="@+id/systemInfoCard"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView android:id="@+id/infoServer"
                style="@style/BodySecondary"
                android:text="服务器: ---"/>
            <TextView android:id="@+id/infoCamera"
                style="@style/BodySecondary"
                android:text="摄像头: ---"/>
            <TextView android:id="@+id/infoMode"
                style="@style/BodySecondary"
                android:text="模式: 空闲"/>
        </LinearLayout>
    </LinearLayout>
</ScrollView>
```

- [ ] **Step 2: 创建 dialog_player_names.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:padding="20dp"
    android:background="@color/bg_card">
    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="@string/dialog_match_title"
        android:textColor="@color/text_primary"
        android:textSize="18sp"
        android:layout_marginBottom="16dp"/>
    <EditText
        android:id="@+id/player1Input"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:hint="@string/hint_player1"
        android:textColor="@color/text_primary"
        android:textColorHint="@color/text_dim"
        android:backgroundTint="@color/accent"
        android:layout_marginBottom="8dp"/>
    <EditText
        android:id="@+id/player2Input"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:hint="@string/hint_player2"
        android:textColor="@color/text_primary"
        android:textColorHint="@color/text_dim"
        android:backgroundTint="@color/accent"
        android:layout_marginBottom="12dp"/>
    <CheckBox
        android:id="@+id/saveDefaultCheck"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="@string/save_as_default"
        android:textColor="@color/text_secondary"
        android:layout_marginBottom="16dp"/>
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal"
        android:gravity="end">
        <Button
            android:id="@+id/btnCancelMatch"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            style="@style/ButtonSecondary"
            android:text="取消"/>
        <Button
            android:id="@+id/btnConfirmMatch"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            style="@style/ButtonPrimary"
            android:text="@string/btn_start_match"
            android:layout_marginStart="12dp"/>
    </LinearLayout>
</LinearLayout>
```

- [ ] **Step 3: 创建 dialog_level_select.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:padding="20dp"
    android:background="@color/bg_card">
    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="@string/dialog_level_title"
        android:textColor="@color/text_primary"
        android:textSize="18sp"
        android:layout_marginBottom="12dp"/>
    <ListView
        android:id="@+id/levelListView"
        android:layout_width="match_parent"
        android:layout_height="300dp"
        android:divider="@color/border_subtle"
        android:dividerHeight="1dp"/>
    <Button
        android:id="@+id/btnCancelLevel"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        style="@style/ButtonSecondary"
        android:text="取消"
        android:layout_gravity="end"/>
</LinearLayout>
```

- [ ] **Step 4: 重写 HomeFragment.java**

```java
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

    @Override
    public void onDestroyView() {
        super.onDestroyView();
        handler.removeCallbacks(infoRefresher);
    }
}
```

- [ ] **Step 5: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: 编译失败 — InProgressFragment 和 SettingsFragment 缺少新方法。后续Task补充。

- [ ] **Step 6: Commit**

```bash
git add phone-app/app/src/main/res/layout/fragment_home.xml \
        phone-app/app/src/main/res/layout/dialog_player_names.xml \
        phone-app/app/src/main/res/layout/dialog_level_select.xml \
        phone-app/app/src/main/java/com/poolar/controller/HomeFragment.java
git commit -m "feat: rewrite HomeFragment with 极简竞技 design, match dialog, and level select dialog"
```

---

### Task 6: 比赛进行中界面 — view_match.xml

**Files:**
- Create: `phone-app/app/src/main/res/layout/view_match.xml`

- [ ] **Step 1: 创建 view_match.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<ScrollView xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/bg_primary"
    android:padding="16dp">
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical">

        <TextView
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="@string/match_in_progress"
            android:textColor="@color/text_primary"
            android:textSize="18sp"
            android:fontFamily="sans-serif-medium"
            android:layout_marginBottom="16dp"/>

        <!-- 双人选手面板 -->
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="horizontal"
            android:layout_marginBottom="16dp">

            <!-- 选手一 -->
            <LinearLayout
                android:id="@+id/player1Card"
                android:layout_width="0dp"
                android:layout_height="wrap_content"
                android:layout_weight="1"
                android:orientation="vertical"
                android:background="@drawable/card_bg"
                android:padding="12dp"
                android:layout_marginEnd="6dp">
                <TextView
                    android:id="@+id/player1Name"
                    style="@style/BodyText"
                    android:text="选手一"/>
                <TextView
                    android:id="@+id/player1Score"
                    style="@style/ScoreNumber"
                    android:text="0"/>
                <TextView
                    android:id="@+id/player1Group"
                    style="@style/BodySecondary"
                    android:text="---"/>
                <TextView
                    android:id="@+id/player1Indicator"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:textColor="@color/accent"
                    android:textSize="12sp"
                    android:visibility="gone"
                    android:text="◀ 击球中"/>
            </LinearLayout>

            <!-- 选手二 -->
            <LinearLayout
                android:id="@+id/player2Card"
                android:layout_width="0dp"
                android:layout_height="wrap_content"
                android:layout_weight="1"
                android:orientation="vertical"
                android:background="@drawable/card_bg"
                android:padding="12dp"
                android:layout_marginStart="6dp">
                <TextView
                    android:id="@+id/player2Name"
                    style="@style/BodyText"
                    android:text="选手二"/>
                <TextView
                    android:id="@+id/player2Score"
                    style="@style/ScoreNumber"
                    android:text="0"/>
                <TextView
                    android:id="@+id/player2Group"
                    style="@style/BodySecondary"
                    android:text="---"/>
                <TextView
                    android:id="@+id/player2Indicator"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:textColor="@color/accent"
                    android:textSize="12sp"
                    android:visibility="gone"
                    android:text="◀ 击球中"/>
            </LinearLayout>
        </LinearLayout>

        <!-- 金色分割线 -->
        <View
            android:layout_width="match_parent"
            android:layout_height="1dp"
            android:layout_marginBottom="16dp"
            android:background="@drawable/divider_gold"/>

        <TextView
            style="@style/Label"
            android:text="@string/label_ball_status"/>

        <!-- 球状态面板 -->
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:background="@drawable/card_bg"
            android:padding="14dp">

            <!-- 纯色球 1-7 -->
            <LinearLayout
                android:id="@+id/solidsRow"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal"
                android:gravity="center"
                android:layout_marginBottom="8dp"/>

            <!-- 黑8 -->
            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal"
                android:gravity="center"
                android:layout_marginBottom="8dp">
                <TextView
                    android:id="@+id/ball8"
                    android:layout_width="36dp"
                    android:layout_height="36dp"
                    android:gravity="center"
                    android:text="⑧"
                    android:textColor="@color/text_primary"
                    android:textSize="16sp"
                    android:background="@drawable/circle_gray"/>
            </LinearLayout>

            <!-- 花色球 9-15 -->
            <LinearLayout
                android:id="@+id/stripesRow"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal"
                android:gravity="center"
                android:layout_marginBottom="10dp"/>

            <!-- 统计行 -->
            <TextView
                android:id="@+id/ballsRemaining"
                style="@style/BodySecondary"
                android:gravity="center"/>
        </LinearLayout>

        <!-- 交换击球按钮 -->
        <Button
            android:id="@+id/btnSwitchTurn"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            style="@style/ButtonSecondary"
            android:text="@string/btn_switch_turn"
            android:layout_gravity="center"
            android:layout_marginTop="16dp"/>
    </LinearLayout>
</ScrollView>
```

- [ ] **Step 2: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Commit**

```bash
git add phone-app/app/src/main/res/layout/view_match.xml
git commit -m "feat: add match in-progress view with dual player cards and ball status grid"
```

---

### Task 7: InProgressFragment 重写 — 比赛模式逻辑

**Files:**
- Modify: `phone-app/app/src/main/res/layout/fragment_progress.xml`
- Modify: `phone-app/app/src/main/java/com/poolar/controller/InProgressFragment.java`

- [ ] **Step 1: 重写 fragment_progress.xml 为容器**

```xml
<?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/progressContainer"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/bg_primary"/>
```

- [ ] **Step 2: 重写 InProgressFragment.java**

```java
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
            com.google.android.material.bottomnavigation.BottomNavigationView nav =
                requireActivity().findViewById(R.id.bottomNav);
            nav.setSelectedItemId(R.id.nav_home);
        });
    }

    private void initBallGrid() {
        // 清空旧View
        solidsRow.removeAllViews();
        stripesRow.removeAllViews();

        int ballSize = 36;
        // 纯色球 1-7
        for (int i = 1; i <= 7; i++) {
            TextView tv = makeBallView(i);
            solidsRow.addView(tv);
        }
        // 花色球 9-15
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
        // 使用圈号Unicode字符 ① ② ③ ...
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
        // 移除所有子View
        container.removeAllViews();

        if ("match".equals(mode)) {
            container.addView(matchView);
        } else if ("training".equals(mode) || "challenge".equals(mode)) {
            container.addView(trainingView);
        } else {
            // idle — 显示占位文字
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
            String winMsg = winner == 1 ? p1Name.getText() + " 获胜！" : p2Name.getText() + " 获胜！";
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

    @Override
    public void onDestroyView() {
        super.onDestroyView();
    }
}
```

- [ ] **Step 3: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -10
```

Expected: 编译失败 — view_training.xml 还不存在。下一个Task创建。

- [ ] **Step 4: Commit**

```bash
git add phone-app/app/src/main/res/layout/fragment_progress.xml \
        phone-app/app/src/main/java/com/poolar/controller/InProgressFragment.java
git commit -m "feat: rewrite InProgressFragment with dynamic mode switching and WebSocket message handling"
```

---

### Task 8: 训练进行中界面 — view_training.xml

**Files:**
- Create: `phone-app/app/src/main/res/layout/view_training.xml`

- [ ] **Step 1: 创建 view_training.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<ScrollView xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/bg_primary"
    android:padding="16dp">
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical">

        <!-- 顶栏：返回 + 档位名 -->
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="horizontal"
            android:gravity="center_vertical"
            android:layout_marginBottom="16dp">
            <Button
                android:id="@+id/btnBackToLevels"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                style="@style/ButtonSecondary"
                android:text="← 返回选关"
                android:textSize="12sp"
                android:minHeight="36dp"
                android:padding="8dp"/>
            <TextView
                android:id="@+id/levelNameText"
                android:layout_width="0dp"
                android:layout_height="wrap_content"
                android:layout_weight="1"
                android:text="---"
                android:textColor="@color/text_primary"
                android:textSize="16sp"
                android:gravity="end"/>
        </LinearLayout>

        <!-- 训练进度 -->
        <TextView style="@style/Label" android:text="@string/label_drill_progress"/>
        <TextView
            android:id="@+id/drillProgressText"
            style="@style/BodyText"
            android:text="第 1 题 / 共 5 题"
            android:layout_marginBottom="8dp"/>
        <ProgressBar
            android:id="@+id/progressBar"
            style="?android:attr/progressBarStyleHorizontal"
            android:layout_width="match_parent"
            android:layout_height="4dp"
            android:progressTint="@color/accent"
            android:progressBackgroundTint="@color/border_medium"
            android:progress="40"/>

        <!-- 摆球要求 -->
        <TextView style="@style/Label" android:text="@string/label_placement"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView android:id="@+id/cuePosText" style="@style/BodyText" android:text="● 白球: ---"/>
            <TextView android:id="@+id/targetPosText" style="@style/BodyText" android:text="○ 目标球: ---"/>
            <TextView android:id="@+id/pocketPosText" style="@style/BodyText" android:text="◎ 目标袋: ---"/>
            <TextView android:id="@+id/techniqueText" style="@style/BodySecondary" android:text="📝 ---"/>
        </LinearLayout>

        <!-- 摆球验证 -->
        <TextView style="@style/Label" android:text="@string/label_placement_verify"/>
        <TextView
            android:id="@+id/placementStatusText"
            style="@style/BodyText"
            android:text="⏳ 等待摆球..."
            android:background="@drawable/card_bg"
            android:padding="12dp"/>

        <!-- 推荐击球 -->
        <TextView style="@style/Label" android:text="@string/label_shot_recommend"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView android:id="@+id/cueTypeText" style="@style/BodyText" android:text="杆法: ---"/>
            <TextView android:id="@+id/powerText" style="@style/BodyText" android:text="力度: ---"/>
            <TextView android:id="@+id/cueLandingText" style="@style/BodySecondary" android:text="走位: ---"/>
        </LinearLayout>

        <!-- 击球结果 -->
        <TextView style="@style/Label" android:text="@string/label_shot_result"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView
                android:id="@+id/shotResultText"
                style="@style/BodyText"
                android:text="⏳ 等待击球..."/>
            <TextView
                android:id="@+id/shotFeedbackText"
                style="@style/BodySecondary"
                android:visibility="gone"/>
        </LinearLayout>

        <!-- 闯关进度 -->
        <TextView style="@style/Label" android:text="@string/label_challenge_progress"/>
        <TextView
            android:id="@+id/consecutiveText"
            style="@style/BodyText"
            android:text="🔥 连续成功 0 次"/>
        <TextView
            android:id="@+id/bestRecordText"
            style="@style/BodySecondary"
            android:text="本关最高: 0 次"/>
        <TextView
            android:id="@+id/totalProgressText"
            style="@style/BodySecondary"
            android:text="总进度: 0%"/>
    </LinearLayout>
</ScrollView>
```

- [ ] **Step 2: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: BUILD SUCCESSFUL（与 Task 7 合在一起后编译通过）

- [ ] **Step 3: Commit**

```bash
git add phone-app/app/src/main/res/layout/view_training.xml
git commit -m "feat: add training in-progress view with drill info, placement verification, and shot result panels"
```

---

### Task 9: SettingsFragment 重写

**Files:**
- Modify: `phone-app/app/src/main/res/layout/fragment_settings.xml`
- Modify: `phone-app/app/src/main/java/com/poolar/controller/SettingsFragment.java`

- [ ] **Step 1: 重写 fragment_settings.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<ScrollView xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/bg_primary"
    android:padding="16dp">
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical">

        <TextView
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="@string/tab_settings"
            android:textColor="@color/text_primary"
            android:textSize="22sp"
            android:fontFamily="sans-serif-medium"
            android:layout_marginBottom="20dp"/>

        <!-- 服务器 -->
        <TextView style="@style/Label" android:text="@string/label_server"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView style="@style/BodySecondary" android:text="IP 地址"/>
            <EditText
                android:id="@+id/hostInput"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_dim"
                android:backgroundTint="@color/accent"
                android:hint="192.168.0.35"
                android:layout_marginBottom="8dp"/>
            <TextView style="@style/BodySecondary" android:text="端口"/>
            <EditText
                android:id="@+id/portInput"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_dim"
                android:backgroundTint="@color/accent"
                android:inputType="number"
                android:hint="8000"
                android:layout_marginBottom="12dp"/>
            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal">
                <Button android:id="@+id/btnDiscover"
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/ButtonSecondary"
                    android:text="🔍 自动发现"
                    android:layout_marginEnd="8dp"/>
                <Button android:id="@+id/btnSave"
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/ButtonPrimary"
                    android:text="💾 保存并重连"/>
            </LinearLayout>
        </LinearLayout>

        <!-- 预览 开关 -->
        <TextView style="@style/Label" android:text="@string/label_preview"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal"
                android:gravity="center_vertical"
                android:layout_marginBottom="10dp">
                <TextView
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/BodyText"
                    android:text="📷 摄像头预览"/>
                <Switch
                    android:id="@+id/toggleCameraPreview"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"/>
            </LinearLayout>
            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal"
                android:gravity="center_vertical">
                <TextView
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/BodyText"
                    android:text="🖥️ 投影预览"/>
                <Switch
                    android:id="@+id/toggleProjectorPreview"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"/>
            </LinearLayout>
        </LinearLayout>

        <!-- 校准 -->
        <TextView style="@style/Label" android:text="@string/label_calibration"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView
                android:id="@+id/calStatus"
                style="@style/BodySecondary"
                android:text="状态: 未校准"
                android:layout_marginBottom="8dp"/>
            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal">
                <Button android:id="@+id/btnCalStart"
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/ButtonPrimary"
                    android:text="开始校准"
                    android:layout_marginEnd="8dp"/>
                <Button android:id="@+id/btnCalStop"
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/ButtonSecondary"
                    android:text="停止"/>
            </LinearLayout>
        </LinearLayout>

        <!-- AI模型 -->
        <TextView style="@style/Label" android:text="@string/label_model"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView
                android:id="@+id/modelStatus"
                style="@style/BodySecondary"
                android:text="已采集: --- 杆 | 模型: ---"
                android:layout_marginBottom="8dp"/>
            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:orientation="horizontal">
                <Button android:id="@+id/btnModelTrain"
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/ButtonSecondary"
                    android:text="AI 训练"
                    android:layout_marginEnd="8dp"/>
                <Button android:id="@+id/btnModelReset"
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_weight="1"
                    style="@style/ButtonSecondary"
                    android:text="重置模型"/>
            </LinearLayout>
        </LinearLayout>

        <!-- 默认选手 -->
        <TextView style="@style/Label" android:text="@string/label_default_players"/>
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            style="@style/CardBase">
            <TextView style="@style/BodySecondary" android:text="选手一"/>
            <EditText
                android:id="@+id/defaultPlayer1"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_dim"
                android:backgroundTint="@color/accent"
                android:hint="张三"
                android:layout_marginBottom="8dp"/>
            <TextView style="@style/BodySecondary" android:text="选手二"/>
            <EditText
                android:id="@+id/defaultPlayer2"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_dim"
                android:backgroundTint="@color/accent"
                android:hint="李四"
                android:layout_marginBottom="8dp"/>
            <Button
                android:id="@+id/btnSavePlayers"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                style="@style/ButtonSecondary"
                android:text="保存默认姓名"/>
        </LinearLayout>

        <!-- 底部信息 -->
        <TextView
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:text="版本 1.0.0"
            android:textColor="@color/text_dim"
            android:textSize="11sp"
            android:gravity="center"
            android:layout_marginTop="24dp"
            android:layout_marginBottom="8dp"/>
    </LinearLayout>
</ScrollView>
```

- [ ] **Step 2: 重写 SettingsFragment.java**

```java
package com.poolar.controller;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CompoundButton;
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
                @Override public void onResult(Void r) { calStatus.setText("状态: 校准中..."); }
                @Override public void onError(String e) { calStatus.setText("状态: 启动失败"); }
            }));
        v.findViewById(R.id.btnCalStop).setOnClickListener(v2 ->
            ApiClient.stopCalibration(new ApiClient.ApiCallback<Void>() {
                @Override public void onResult(Void r) { calStatus.setText("状态: 已停止"); }
                @Override public void onError(String e) {}
            }));

        // AI模型
        modelStatus = v.findViewById(R.id.modelStatus);
        v.findViewById(R.id.btnModelTrain).setOnClickListener(v2 ->
            ApiClient.post("/api/ai-train/start", null, ok ->
                Toast.makeText(getContext(), ok ? "AI训练已开始" : "训练启动失败", Toast.LENGTH_SHORT).show()));
        v.findViewById(R.id.btnModelReset).setOnClickListener(v2 ->
            new android.app.AlertDialog.Builder(getContext())
                .setTitle("重置模型")
                .setMessage("确定要重置AI模型吗？所有学习数据将丢失。")
                .setPositiveButton("确定", (d, w) ->
                    ApiClient.post("/api/ai-train/reset", null, ok ->
                        Toast.makeText(getContext(), ok ? "模型已重置" : "重置失败", Toast.LENGTH_SHORT).show()))
                .setNegativeButton("取消", null)
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
            Toast.makeText(getContext(), "已保存", Toast.LENGTH_SHORT).show();
        });

        return v;
    }

    private void saveAndReconnect(SharedPreferences prefs) {
        String host = hostInput.getText().toString().trim();
        int port = Integer.parseInt(portInput.getText().toString().trim());
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

    @Override
    public void onDestroyView() {
        super.onDestroyView();
        if (cameraPreviewWs != null) cameraPreviewWs.disconnect();
        if (projectorPreviewWs != null) projectorPreviewWs.disconnect();
    }
}
```

- [ ] **Step 3: 验证编译**

```bash
cd "D:\daima\phone-app" && ./gradlew assembleDebug 2>&1 | tail -10
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Commit**

```bash
git add phone-app/app/src/main/res/layout/fragment_settings.xml \
        phone-app/app/src/main/java/com/poolar/controller/SettingsFragment.java
git commit -m "feat: rewrite SettingsFragment with 极简竞技 design, preview toggles, and default player names"
```

---

### Task 10: 集成验证 + 清理

**Files:**
- No new files — verify full build passes

- [ ] **Step 1: 完整编译验证**

```bash
cd "D:\daima\phone-app" && ./gradlew clean assembleDebug 2>&1 | tail -20
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 2: 检查 AndroidManifest.xml 不需要修改**

确认 `android:usesCleartextTraffic="true"` 保留（WebSocket明文连接需要）。确认主题引用 `@style/Theme.PoolAR`。

- [ ] **Step 3: Commit (如有遗漏文件)**

```bash
git status
# 如有未追踪文件，git add 并提交
```

---

## 实现顺序

```
Task 1 (资源文件) ──┐
                    ├─→ Task 3 (WebSocketClient) ──→ Task 4 (MainActivity)
Task 2 (styles)   ──┘                                     │
                                                          ▼
Task 5 (HomeFragment + dialogs) ←──────────────────────────┘
    │
    ▼
Task 6 (view_match.xml) ──→ Task 7 (InProgressFragment)
    │
    ▼
Task 8 (view_training.xml)
    │
    ▼
Task 9 (SettingsFragment)
    │
    ▼
Task 10 (集成验证)
```

Task 1和2可并行。Task 5在Task 4之后。Task 6和8独立，Task 7居中串联。
