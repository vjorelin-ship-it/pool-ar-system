# USB摄像头 + 安卓盒子 实现计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 按任务逐条实现。步骤使用 `- [ ]` checkbox 语法追踪。

**目标:** 将摄像头从WiFi RTSP切换到USB UVC，安卓盒子采集+发送帧，后端通过WebSocket接收处理

**架构:** 安卓盒子Camera2采集→硬编码JPEG→WebSocket发送→后端ws_camera接收→视觉管线(不变)。投影接收链路不变。后端通过`CAMERA_SOURCE`配置切换RTSP/USB模式。

**技术栈:** Android Camera2 API, Java-WebSocket, Python FastAPI WebSocket, OpenCV

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/camera/ws_camera.py` | 新建 | WebSocket帧接收器，接口对齐RtspCamera |
| `backend/api/websocket.py` | 修改 | 新增`/api/ws/camera-upload`端点 |
| `backend/config.py` | 修改 | 新增`CAMERA_SOURCE`配置 |
| `backend/main.py` | 修改 | 根据配置选择摄像头源 |
| `projector-app/.../CameraCapture.java` | 新建 | Camera2 API采集+JPEG编码 |
| `projector-app/.../MainActivity.java` | 修改 | 集成摄像头+双WebSocket |
| `projector-app/.../AndroidManifest.xml` | 修改 | 添加CAMERA权限 |
| `docs/DEVELOPMENT.md` | 修改 | 更新硬件架构 |

---

### Task 1: WebSocket帧接收器

**文件:**
- 新建: `backend/camera/ws_camera.py`

**职责:** 从WebSocket接收JPEG帧，解码为OpenCV Mat，封装为Frame对象，接口与RtspCamera完全一致。

- [ ] **Step 1: 创建文件**

```python
# backend/camera/ws_camera.py
"""WebSocket摄像头帧接收器 — 从安卓盒子WebSocket接收USB摄像头帧

接口与RtspCamera完全一致：start() / stop() / get_frame() / is_running()
"""
import threading
import time
import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class Frame:
    data: Optional['cv2.Mat']  # numpy array (H, W, 3) BGR
    timestamp: float
    valid: bool


class WebSocketCamera:
    """从WebSocket接收摄像头帧"""

    def __init__(self):
        self._latest_frame: Optional[Frame] = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_count = 0
        self._last_receive_time = 0.0

    def start(self) -> None:
        self._running = True
        self._frame_count = 0

    def stop(self) -> None:
        self._running = False
        with self._lock:
            self._latest_frame = None

    def get_frame(self) -> Optional[Frame]:
        with self._lock:
            return self._latest_frame

    def is_running(self) -> bool:
        return self._running

    def receive_frame(self, jpeg_bytes: bytes, timestamp: float) -> None:
        """由WebSocket handler在接收线程调用"""
        if not self._running:
            return
        import cv2
        data = cv2.imdecode(
            np.frombuffer(jpeg_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if data is None:
            return
        with self._lock:
            self._latest_frame = Frame(
                data=data,
                timestamp=timestamp,
                valid=True,
            )
            self._frame_count += 1
            self._last_receive_time = time.time()

    def stats(self) -> dict:
        with self._lock:
            return {
                "frame_count": self._frame_count,
                "last_receive": self._last_receive_time,
                "running": self._running,
            }
```

- [ ] **Step 2: 验证独立可运行**

```bash
cd "D:\daima\backend" && python -c "
from camera.ws_camera import WebSocketCamera, Frame
c = WebSocketCamera()
c.start()
# 模拟接收一帧黑色JPEG
import cv2, numpy as np
_, jpeg = cv2.imencode('.jpg', np.zeros((720,1280,3), dtype=np.uint8))
c.receive_frame(jpeg.tobytes(), 0.0)
f = c.get_frame()
assert f is not None and f.valid
assert f.data.shape == (720, 1280, 3)
print('WebSocketCamera OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/camera/ws_camera.py
git commit -m "feat: add WebSocket camera frame receiver with RtspCamera-compatible interface"
```

---

### Task 2: WebSocket端点 + 配置 + main集成

**文件:**
- 修改: `backend/api/websocket.py` 追加 `/api/ws/camera-upload` 端点
- 修改: `backend/config.py` 追加 `CAMERA_SOURCE`
- 修改: `backend/main.py` 按配置选择摄像头源

- [ ] **Step 1: 追加WebSocket端点**

在 `ConnectionManager` 类中追加：

```python
    # ─── Camera Upload (USB camera frames from Android box) ───

    async def connect_camera_upload(self, ws: WebSocket) -> None:
        await ws.accept()
        self._camera_upload_clients: set = getattr(self, '_camera_upload_clients', set())
        self._camera_upload_clients.add(ws)
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                    if data.get("type") == "camera_frame":
                        import base64
                        jpeg_bytes = base64.b64decode(data["data"])
                        ts = data.get("timestamp", time.time())
                        cam = system_state.get("ws_camera")
                        if cam is not None:
                            cam.receive_frame(jpeg_bytes, ts)
                except Exception:
                    pass
        except WebSocketDisconnect:
            self._camera_upload_clients.discard(ws)

    def has_camera_upload_clients(self) -> bool:
        s = getattr(self, '_camera_upload_clients', set())
        return len(s) > 0
```

在 `api/routes.py` 中追加路由（在已有WebSocket端点之后）：

```python
@router.websocket("/ws/camera-upload")
async def camera_upload_websocket(ws: WebSocket):
    await manager.connect_camera_upload(ws)
```

- [ ] **Step 2: 修改config.py**

```python
# 在 config.py 中追加
CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "rtsp")  # "rtsp" | "websocket"
```

- [ ] **Step 3: 修改main.py — start()方法**

在 `PoolARSystem.start()` 中，将现有的摄像头启动代码改为：

```python
        from config import settings
        if settings.CAMERA_SOURCE == "websocket":
            from camera.ws_camera import WebSocketCamera
            self.camera = WebSocketCamera()
            self.camera.start()
            system_state["ws_camera"] = self.camera
            system_state["camera"] = self.camera
            print("[Camera] WebSocket camera mode (waiting for Android box)")
        else:
            self.camera = RtspCamera(
                settings.CAMERA_RTSP_URL, settings.CAMERA_FPS)
            self.camera.start()
            system_state["camera"] = self.camera
            print(f"[Camera] Connected to {settings.CAMERA_RTSP_URL}")
```

- [ ] **Step 4: 验证导入链**

```bash
cd "D:\daima\backend" && python -c "
import os; os.environ['CAMERA_SOURCE'] = 'websocket'
from config import settings
assert settings.CAMERA_SOURCE == 'websocket'
from camera.ws_camera import WebSocketCamera
c = WebSocketCamera()
c.start()
print('Config + camera OK')
c.stop()
"
```

- [ ] **Step 5: Commit**

```bash
git add backend/api/websocket.py backend/api/routes.py backend/config.py backend/main.py
git commit -m "feat: add /api/ws/camera-upload endpoint and CAMERA_SOURCE config for USB camera"
```

---

### Task 3: Android Camera2 采集模块

**文件:**
- 新建: `projector-app/app/src/main/java/com/poolar/projector/CameraCapture.java`

**职责:** 打开USB UVC摄像头，2K@60采集，硬件JPEG编码，回调输出JPEG字节数组。

- [ ] **Step 1: 创建CameraCapture.java**

```java
package com.poolar.projector;

import android.content.Context;
import android.graphics.ImageFormat;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;
import android.view.Surface;

import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.Collections;

public class CameraCapture {
    private static final String TAG = "CameraCapture";
    private CameraManager cameraManager;
    private CameraDevice cameraDevice;
    private CameraCaptureSession captureSession;
    private ImageReader imageReader;
    private Handler backgroundHandler;
    private HandlerThread backgroundThread;
    private FrameCallback frameCallback;
    private int targetWidth = 2560;
    private int targetHeight = 1440;

    public interface FrameCallback {
        void onFrame(byte[] jpegData, long timestamp);
    }

    public CameraCapture(Context context, FrameCallback callback) {
        this.cameraManager = (CameraManager) context.getSystemService(Context.CAMERA_SERVICE);
        this.frameCallback = callback;
    }

    public void setResolution(int width, int height) {
        this.targetWidth = width;
        this.targetHeight = height;
    }

    public void start() {
        startBackgroundThread();
        try {
            String cameraId = findUsbCamera();
            if (cameraId == null) {
                Log.w(TAG, "No USB camera found, using first available");
                cameraId = cameraManager.getCameraIdList()[0];
            }
            Log.d(TAG, "Opening camera: " + cameraId);
            cameraManager.openCamera(cameraId, stateCallback, backgroundHandler);
        } catch (SecurityException e) {
            Log.e(TAG, "Camera permission denied", e);
        } catch (CameraAccessException e) {
            Log.e(TAG, "Camera access error", e);
        }
    }

    public void stop() {
        try {
            if (captureSession != null) {
                captureSession.close();
                captureSession = null;
            }
        } catch (Exception e) { Log.e(TAG, "Error closing session", e); }
        try {
            if (cameraDevice != null) {
                cameraDevice.close();
                cameraDevice = null;
            }
        } catch (Exception e) { Log.e(TAG, "Error closing camera", e); }
        if (imageReader != null) {
            imageReader.close();
            imageReader = null;
        }
        stopBackgroundThread();
    }

    private String findUsbCamera() throws CameraAccessException {
        for (String id : cameraManager.getCameraIdList()) {
            CameraCharacteristics chars = cameraManager.getCameraCharacteristics(id);
            Integer facing = chars.get(CameraCharacteristics.LENS_FACING);
            if (facing != null && facing == CameraCharacteristics.LENS_FACING_EXTERNAL) {
                return id;
            }
        }
        return null;
    }

    private final CameraDevice.StateCallback stateCallback = new CameraDevice.StateCallback() {
        @Override
        public void onOpened(CameraDevice device) {
            cameraDevice = device;
            createCaptureSession();
        }
        @Override
        public void onDisconnected(CameraDevice device) {
            device.close();
            cameraDevice = null;
            Log.w(TAG, "Camera disconnected, retrying in 3s");
            new Handler(backgroundThread.getLooper()).postDelayed(() -> start(), 3000);
        }
        @Override
        public void onError(CameraDevice device, int error) {
            device.close();
            cameraDevice = null;
            Log.e(TAG, "Camera error: " + error);
        }
    };

    private void createCaptureSession() {
        try {
            imageReader = ImageReader.newInstance(
                targetWidth, targetHeight, ImageFormat.JPEG, 2);
            imageReader.setOnImageAvailableListener(readerListener, backgroundHandler);

            cameraDevice.createCaptureSession(
                Collections.singletonList(imageReader.getSurface()),
                sessionCallback, backgroundHandler);
        } catch (CameraAccessException e) {
            Log.e(TAG, "Failed to create capture session", e);
        }
    }

    private final CameraCaptureSession.StateCallback sessionCallback =
        new CameraCaptureSession.StateCallback() {
            @Override
            public void onConfigured(CameraCaptureSession session) {
                captureSession = session;
                startCapture();
            }
            @Override
            public void onConfigureFailed(CameraCaptureSession session) {
                Log.e(TAG, "Session configuration failed");
            }
        };

    private void startCapture() {
        try {
            CaptureRequest.Builder builder = cameraDevice.createCaptureRequest(
                CameraDevice.TEMPLATE_STILL_CAPTURE);
            builder.addTarget(imageReader.getSurface());
            builder.set(CaptureRequest.JPEG_QUALITY, (byte) 70);
            captureSession.setRepeatingRequest(builder.build(), null, backgroundHandler);
        } catch (CameraAccessException e) {
            Log.e(TAG, "Failed to start capture", e);
        }
    }

    private final ImageReader.OnImageAvailableListener readerListener =
        new ImageReader.OnImageAvailableListener() {
            @Override
            public void onImageAvailable(ImageReader reader) {
                Image image = reader.acquireLatestImage();
                if (image == null) return;
                try {
                    ByteBuffer buffer = image.getPlanes()[0].getBuffer();
                    byte[] jpegData = new byte[buffer.remaining()];
                    buffer.get(jpegData);
                    if (frameCallback != null) {
                        frameCallback.onFrame(jpegData, image.getTimestamp());
                    }
                } finally {
                    image.close();
                }
            }
        };

    private void startBackgroundThread() {
        backgroundThread = new HandlerThread("CameraBackground");
        backgroundThread.start();
        backgroundHandler = new Handler(backgroundThread.getLooper());
    }

    private void stopBackgroundThread() {
        if (backgroundThread != null) {
            backgroundThread.quitSafely();
            try { backgroundThread.join(); } catch (InterruptedException e) {}
            backgroundThread = null;
            backgroundHandler = null;
        }
    }
}
```

- [ ] **Step 2: 验证代码可编译（IDE检查）**

无需命令行编译，确认类结构完整即可。

- [ ] **Step 3: Commit**

```bash
git add projector-app/app/src/main/java/com/poolar/projector/CameraCapture.java
git commit -m "feat: add Camera2 capture module for USB UVC camera at 2K@60"
```

---

### Task 4: Android MainActivity集成 + 双WebSocket

**文件:**
- 修改: `projector-app/app/src/main/java/com/poolar/projector/MainActivity.java`
- 修改: `projector-app/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: 修改AndroidManifest.xml**

在 `<manifest>` 内追加权限：

```xml
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-feature android:name="android.hardware.camera" android:required="false" />
    <uses-feature android:name="android.hardware.camera.external" android:required="false" />
    <uses-feature android:name="android.hardware.usb.host" android:required="false" />
```

- [ ] **Step 2: 重写MainActivity.java**

核心改动：
1. 添加 `CameraCapture` 成员和帧回调
2. 添加第二个WebSocket连接（摄像头上传通道）
3. 在 `onCreate` 中启动摄像头采集
4. 在 `onDestroy` 中停止摄像头

```java
package com.poolar.projector;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.Handler;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import com.google.gson.JsonObject;
import com.google.gson.Gson;

import java.net.URI;
import java.util.Locale;

public class MainActivity extends Activity implements TextToSpeech.OnInitListener {
    private ImageView projectionView;
    private TextView statusText;
    private WebSocketClient wsProjectorClient;   // 接收投影画面
    private WebSocketClient wsCameraClient;      // 发送摄像头帧
    private Handler reconnectHandler = new Handler();
    private TextToSpeech tts;
    private boolean ttsReady = false;
    private CameraCapture cameraCapture;
    private Gson gson = new Gson();
    private int frameSkipCounter = 0;
    private static final int FRAME_SKIP = 3;      // 每3帧发1帧 (~20 FPS)
    private static final String TAG = "PoolARProjector";
    private static final String DEFAULT_HOST = "192.168.0.35";
    private static final int DEFAULT_PORT = 8000;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        setContentView(R.layout.activity_projection);
        projectionView = findViewById(R.id.projectionView);
        statusText = findViewById(R.id.statusText);
        statusText.setOnLongClickListener(v -> {
            showSettingsDialog();
            return true;
        });

        tts = new TextToSpeech(this, this);

        // 启动摄像头采集
        startCameraCapture();

        // 连接投影WebSocket
        connectProjectorWebSocket();
        // 连接摄像头上传WebSocket
        connectCameraWebSocket();
    }

    // ─── Camera ──────────────────────────────────────────────

    private void startCameraCapture() {
        cameraCapture = new CameraCapture(this, (jpegData, timestamp) -> {
            frameSkipCounter++;
            if (frameSkipCounter % FRAME_SKIP != 0) return;

            if (wsCameraClient != null && wsCameraClient.isOpen()) {
                try {
                    String b64 = Base64.encodeToString(jpegData, Base64.NO_WRAP);
                    JsonObject msg = new JsonObject();
                    msg.addProperty("type", "camera_frame");
                    msg.addProperty("width", 2560);
                    msg.addProperty("height", 1440);
                    msg.addProperty("timestamp", timestamp);
                    msg.addProperty("frame_id", frameSkipCounter / FRAME_SKIP);
                    msg.addProperty("data", b64);
                    wsCameraClient.send(gson.toJson(msg));
                } catch (Exception e) {
                    Log.e(TAG, "Camera send error", e);
                }
            }
        });
        cameraCapture.start();
    }

    // ─── TTS ─────────────────────────────────────────────────

    @Override
    public void onInit(int status) {
        if (status == TextToSpeech.SUCCESS) {
            int result = tts.setLanguage(Locale.CHINESE);
            if (result == TextToSpeech.LANG_MISSING_DATA
                || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                Log.w(TAG, "TTS: Chinese not supported");
            } else {
                ttsReady = true;
                Log.d(TAG, "TTS ready");
            }
        }
    }

    private void speak(String text) {
        if (ttsReady && tts != null) {
            tts.speak(text, TextToSpeech.QUEUE_ADD, null, null);
        }
    }

    // ─── Settings ────────────────────────────────────────────

    private String host() {
        return getSharedPreferences("prefs", MODE_PRIVATE)
            .getString("server_host", DEFAULT_HOST);
    }

    private int port() {
        return getSharedPreferences("prefs", MODE_PRIVATE)
            .getInt("server_port", DEFAULT_PORT);
    }

    private void showSettingsDialog() {
        String current = "ws://" + host() + ":" + port();
        EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT);
        input.setText(current);
        input.setSelectAllOnFocus(true);
        new AlertDialog.Builder(this)
            .setTitle("设置服务器地址")
            .setMessage("当前: " + current)
            .setView(input)
            .setPositiveButton("连接", (d, w) -> {
                String url = input.getText().toString().trim();
                if (!url.isEmpty()) {
                    try {
                        URI uri = new URI(url);
                        getSharedPreferences("prefs", MODE_PRIVATE)
                            .edit()
                            .putString("server_host", uri.getHost())
                            .putInt("server_port", uri.getPort() <= 0 ? DEFAULT_PORT : uri.getPort())
                            .apply();
                    } catch (Exception e) {
                        Log.e(TAG, "Invalid URL", e);
                    }
                    reconnectAll();
                }
            })
            .setNegativeButton("取消", null)
            .show();
    }

    private void reconnectAll() {
        if (wsProjectorClient != null) wsProjectorClient.close();
        if (wsCameraClient != null) wsCameraClient.close();
        statusText.setText("正在重连...");
        connectProjectorWebSocket();
        connectCameraWebSocket();
    }

    // ─── WebSocket: Projector (接收投影画面) ──────────────────

    private void connectProjectorWebSocket() {
        String url = "ws://" + host() + ":" + port() + "/api/ws/projector";
        try {
            wsProjectorClient = new WebSocketClient(new URI(url)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    runOnUiThread(() -> {
                        statusText.setText("投影已连接");
                        statusText.setVisibility(View.VISIBLE);
                    });
                    Log.d(TAG, "Projector WS connected");
                }
                @Override
                public void onMessage(String message) {
                    try {
                        JsonObject json = gson.fromJson(message, JsonObject.class);
                        String type = json.get("type").getAsString();
                        if ("projection".equals(type)) {
                            byte[] imgBytes = Base64.decode(
                                json.get("image").getAsString(), Base64.DEFAULT);
                            final Bitmap bitmap = BitmapFactory.decodeByteArray(
                                imgBytes, 0, imgBytes.length);
                            runOnUiThread(() -> {
                                projectionView.setImageBitmap(bitmap);
                                statusText.setVisibility(View.GONE);
                            });
                        } else if ("announce".equals(type)) {
                            String text = json.get("text").getAsString();
                            speak(text);
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Projector message error", e);
                    }
                }
                @Override
                public void onClose(int code, String reason, boolean remote) {
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.VISIBLE);
                        statusText.setText("投影断开，3秒后重连");
                    });
                    reconnectHandler.postDelayed(
                        MainActivity.this::connectProjectorWebSocket, 3000);
                }
                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "Projector WS error", ex);
                }
            };
            wsProjectorClient.connect();
        } catch (Exception e) {
            Log.e(TAG, "Projector connect failed", e);
            reconnectHandler.postDelayed(
                MainActivity.this::connectProjectorWebSocket, 3000);
        }
    }

    // ─── WebSocket: Camera Upload (发送摄像头帧) ──────────────

    private void connectCameraWebSocket() {
        String url = "ws://" + host() + ":" + port() + "/api/ws/camera-upload";
        try {
            wsCameraClient = new WebSocketClient(new URI(url)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    Log.d(TAG, "Camera upload WS connected");
                    runOnUiThread(() -> showToast("摄像头已连接"));
                }
                @Override
                public void onMessage(String message) {
                    // 后端可发送帧率控制等指令
                }
                @Override
                public void onClose(int code, String reason, boolean remote) {
                    Log.w(TAG, "Camera upload closed: " + reason);
                    reconnectHandler.postDelayed(
                        MainActivity.this::connectCameraWebSocket, 3000);
                }
                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "Camera upload WS error", ex);
                }
            };
            wsCameraClient.connect();
        } catch (Exception e) {
            Log.e(TAG, "Camera connect failed", e);
            reconnectHandler.postDelayed(
                MainActivity.this::connectCameraWebSocket, 3000);
        }
    }

    // ─── Lifecycle ───────────────────────────────────────────

    @Override
    protected void onDestroy() {
        if (cameraCapture != null) cameraCapture.stop();
        if (tts != null) { tts.stop(); tts.shutdown(); }
        reconnectHandler.removeCallbacksAndMessages(null);
        if (wsProjectorClient != null) wsProjectorClient.close();
        if (wsCameraClient != null) wsCameraClient.close();
        super.onDestroy();
    }

    private void showToast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add projector-app/app/src/main/java/com/poolar/projector/MainActivity.java \
        projector-app/app/src/main/AndroidManifest.xml
git commit -m "feat: integrate CameraCapture with dual WebSocket in projector app"
```

---

### Task 5: 文档更新 + 集成验证

- [ ] **Step 1: 更新DEVELOPMENT.md**

在 `docs/DEVELOPMENT.md` 第2节硬件架构中，更新摄像头行：

```
| USB摄像头 | 2K@60FPS UVC免驱，2.8mm焦距，吊顶安装 | 拍摄桌面，插在安卓盒子上 |
```

更新网络拓扑图，将"WiFi摄像头"替换为"USB摄像头 ─USB─► 安卓盒子 ─WiFi 6 WebSocket─► 电脑后端"。

- [ ] **Step 2: 后端集成验证**

```bash
cd "D:\daima\backend" && python -c "
import os; os.environ['CAMERA_SOURCE'] = 'websocket'
from camera.ws_camera import WebSocketCamera
from main import PoolARSystem
s = PoolARSystem()
# 验证WebSocket摄像头模式初始化
assert s.camera is not None
assert s.camera.is_running()
print('WebSocket camera integration OK')
s.stop()
"
```

- [ ] **Step 3: Commit**

```bash
git add docs/DEVELOPMENT.md
git commit -m "docs: update hardware architecture for USB camera + Android box"
```

---

## 实现顺序

1. Task 1 → WebSocket帧接收器（独立，无依赖）
2. Task 2 → 后端WebSocket端点 + 配置集成（依赖Task 1）
3. Task 3 → Android Camera2采集模块（独立，无依赖）
4. Task 4 → Android MainActivity集成（依赖Task 3）
5. Task 5 → 文档+验证（依赖Task 2、4）

Task 1和Task 3可并行，Task 2和Task 4可并行（各自独立）。
