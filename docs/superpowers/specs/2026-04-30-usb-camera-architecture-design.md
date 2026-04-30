# USB摄像头 + 安卓盒子架构设计

> 版本: 1.0 | 日期: 2026-04-30 | 状态: 设计阶段

## 1. 设计目标

用 USB 摄像头（插安卓盒子）替代独立的 WiFi RTSP 摄像头，安卓盒子同时负责采集视频帧发送到后端、接收后端渲染的投影画面并输出到投影仪显示。

---

## 2. 硬件架构

### 2.1 设备清单

| 设备 | 规格 | 用途 |
|------|------|------|
| 💻 电脑后端 (Windows) | RX 7900 XTX, 32GB RAM | 视觉识别、物理/AI计算、API服务 |
| 📦 安卓盒子 | RK3588 / S928X, USB 3.0, WiFi 6, Android 12+ | 摄像头采集、帧发送、投影接收、HDMI输出 |
| 📷 USB摄像头 | 2K (2560×1440) @ 60FPS, UVC免驱, 2.8mm焦距 | 拍摄桌面 |
| 📽️ 普通投影仪 | 1080p+, HDMI输入, 高亮度 | 显示投影画面 |
| 📱 安卓手机 | 用户现有设备 | 控制APP |
| 🖥️ 液晶屏 | VGA接口 | 比分网页 |

### 2.2 物理连接

```
                    ┌─────────────────────┐
                    │   📷 USB摄像头       │
                    │   2K@60FPS UVC      │
                    │   吊顶俯拍桌面       │
                    └──────────┬──────────┘
                               │ USB 3.0 线 (≥3m)
                               ▼
┌──────────┐  HDMI  ┌─────────────────────┐  WiFi 6  ┌──────────────────┐
│ 📽️ 投影仪 │◄───────│   📦 安卓盒子        │◄────────►│  💻 电脑后端       │
│ (纯显示)  │        │   RK3588/S928X     │          │  Windows          │
│          │        │                     │          │                  │
└──────────┘        │  采集+编码+发送帧    │          │  视觉+物理+渲染   │
                    │  接收+解码+显示投影  │          │  API + WebSocket │
                    └─────────────────────┘          └────────┬─────────┘
                                                             │ HTTP/WS
                                                    ┌────────┴─────────┐
                                                    ▼                  ▼
                                               📱 手机APP        🖥️ 比分液晶屏
```

### 2.3 网络拓扑

```
📦 安卓盒子 ──── WiFi 6 ──── 🌐 路由器 ──── 网线 ──── 💻 电脑后端
                                                       │
                                                   HTTP/WebSocket
                                                       │
                                            ┌──────────┴──────────┐
                                            ▼                      ▼
                                       📱 安卓手机            🖥️ 比分液晶屏
```

---

## 3. 数据流

### 3.1 完整链路

```
USB摄像头
  │ 2K@60 raw帧 (~11MB/帧)
  ▼
安卓盒子 Camera2 API
  │ GPU硬编码 JPEG 质量70 (~300KB/帧)
  │ 编码耗时: ~5ms
  ▼
安卓盒子 WebSocket 发送
  │ WiFi 6 上传: ~2ms
  │ 带宽消耗: ~18 Mbps
  ▼
电脑后端 WebSocket 接收
  │ OpenCV 解码: ~3ms
  ▼
视觉管线
  │ 桌检测 → 透视矫正 → 下采样到1200×600
  │ 球检测 (ML优先→传统CV兜底)
  │ 耗时: ~15ms
  ▼
轨迹计算
  │ Diffusion模型: ~45ms (或物理引擎: ~3ms)
  ▼
投影渲染
  │ 1920×1080 路线渲染
  │ JPEG编码 质量85: ~8ms
  ▼
电脑后端 WebSocket 发送
  │ WiFi 6 下载: ~3ms
  ▼
安卓盒子 WebSocket 接收
  │ 解码: ~3ms
  ▼
HDMI输出到投影仪
  │ 显示延迟: ~10ms (投影仪自身)
  ▼
投影仪屏幕显示
```

**关键延迟汇总：**

| 阶段 | 耗时 |
|------|------|
| 摄像头→安卓→编码→发送 | ~7ms |
| 网络（WiFi 6往返） | ~5ms |
| 视觉+AI+渲染 | ~68ms |
| 投影仪显示延迟 | ~10ms |
| **总延迟** | **~90ms (11 FPS等效)** |

对于台球击球→投影更新场景，90ms 延迟完全可用。

### 3.2 帧率权衡

| 采集帧率 | 后端处理间隔 | 投影更新率 | 实际延迟 |
|----------|-------------|-----------|----------|
| 60 FPS | 每3帧处理1帧 | 20 FPS | ~90ms |
| 60 FPS | 每帧处理 | 60 FPS | ~90ms (AI排队) |
| 30 FPS | 每帧处理 | 30 FPS | ~100ms |

**推荐 60FPS 采集，后端每3帧做一次完整检测，投影像间补传桌面轮廓帧。** 运动流畅，AI不排队。

---

## 4. 软件改动

### 4.1 安卓盒子 APP（projector-app 改造）

当前 projector-app 只接收投影画面并显示。需要增加：

```
projector-app/app/src/main/java/com/poolar/projector/
├── MainActivity.java          # 改造：接收+发送双WebSocket
├── CameraCapture.java         # 新增：Camera2 API 采集
├── CameraEncoder.java         # 新增：硬件JPEG编码
├── CameraFrameSender.java     # 新增：WebSocket发送帧
├── ProjectionReceiver.java    # 新增：WebSocket接收投影
├── BootReceiver.java          # 不变：开机自启动
└── CameraPreviewView.java     # 新增：采集预览（调试用）
```

**核心功能：**

| 组件 | 职责 |
|------|------|
| CameraCapture | Camera2 API打开USB UVC设备，2K@60采集 |
| CameraEncoder | 用 Android MediaCodec 或 Bitmap.compress 做JPEG硬件编码 |
| CameraFrameSender | WebSocket发送 `{"type":"camera_frame","data":"<base64 JPEG>"}` |
| ProjectionReceiver | WebSocket接收 `{"type":"projection","data":"<base64 JPEG>"}`，解码显示 |

**WebSocket 协议（盒子→后端）：**

```json
{
  "type": "camera_frame",
  "width": 2560,
  "height": 1440,
  "timestamp": 1714298400501,
  "frame_id": 1042,
  "data": "base64_encoded_jpeg..."
}
```

**双WebSocket连接：**
- 发送通道：`ws://<server>:8000/api/ws/camera-upload`（盒子→后端，单向）
- 接收通道：`ws://<server>:8000/api/ws/projector`（后端→盒子，单向，保持不变）

### 4.2 电脑后端改动

| 文件 | 改动 |
|------|------|
| `backend/camera/rtsp_camera.py` | 保留但不再默认使用 |
| `backend/camera/ws_camera.py` | **新增**：WebSocket帧接收，模拟Frame接口 |
| `backend/api/websocket.py` | **新增**：`/api/ws/camera-upload`端点，管理上传客户端 |
| `backend/main.py` | 修改：根据配置选择RTSP或WebSocket摄像头源 |
| `backend/config.py` | 修改：新增 `CAMERA_SOURCE` 选项 |

**WebSocket帧接收器（ws_camera.py）：**

```python
class WebSocketCamera:
    """从WebSocket接收摄像头帧，接口对齐RtspCamera"""
    
    def __init__(self):
        self._latest_frame: Optional[Frame] = None
        self._lock = threading.Lock()
        self._running = False
    
    def start(self) -> None:
        self._running = True
    
    def stop(self) -> None:
        self._running = False
    
    def get_frame(self) -> Optional[Frame]:
        with self._lock:
            return self._latest_frame
    
    def receive_frame(self, jpeg_bytes: bytes, timestamp: float) -> None:
        """由WebSocket handler调用"""
        if not self._running:
            return
        data = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
        with self._lock:
            self._latest_frame = Frame(data=data, timestamp=timestamp, valid=True)
```

**WebSocket端点（websocket.py新增）：**

```python
# /api/ws/camera-upload — 盒子发送摄像头帧
async def connect_camera_upload(self, ws: WebSocket):
    await ws.accept()
    self._camera_upload_clients.add(ws)
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if data.get("type") == "camera_frame":
                jpeg_bytes = base64.b64decode(data["data"])
                ts = data.get("timestamp", time.time())
                system_state["ws_camera"].receive_frame(jpeg_bytes, ts)
    except WebSocketDisconnect:
        self._camera_upload_clients.discard(ws)
```

### 4.3 配置文件改动

```python
# config.py
CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "websocket")  # "rtsp" | "websocket"
CAMERA_RTSP_URL = os.getenv("CAMERA_RTSP_URL", "")       # 仅RTSP模式使用
```

### 4.4 手机APP — 无需改动

手机APP连接电脑后端，与摄像头来源无关。

---

## 5. 后端处理管线调整

```
当前: RTSP线程采集 → 主循环读帧 → 处理 → 投影
改造: WebSocket接收帧 → 存入共享Buffer → 主循环读帧 → 处理 → 投影
```

接口保持一致（`get_frame() → Optional[Frame]`），`_vision_loop` 不需要改动。

### 5.1 帧缓冲策略

```
WebSocket线程接收帧 → 写入环形缓冲 (容量2帧)
主循环读取     → 取最新帧 → 处理

如果主循环处理慢，旧帧自动被新帧覆盖（不排队）
```

---

## 6. Android盒子APP升级详情

### 6.1 权限

```xml
<!-- AndroidManifest.xml 新增 -->
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.INTERNET" />
<uses-feature android:name="android.hardware.camera" />
<uses-feature android:name="android.hardware.usb.host" />
```

### 6.2 Camera2 采集配置

```java
// CameraCapture.java
// 打开USB UVC摄像头
String[] cameraIds = manager.getCameraIdList();
// USB摄像头通常是外置摄像头 (LENS_FACING_EXTERNAL)
String usbCameraId = null;
for (String id : cameraIds) {
    CameraCharacteristics chars = manager.getCameraCharacteristics(id);
    Integer facing = chars.get(CameraCharacteristics.LENS_FACING);
    if (facing != null && facing == CameraCharacteristics.LENS_FACING_EXTERNAL) {
        usbCameraId = id;
        break;
    }
}
// Fallback: 取第一个后置
if (usbCameraId == null) {
    usbCameraId = cameraIds[0];
}

// 设置采集参数
// 2560×1440 @ 60FPS
// YUV_420_888 格式
// 硬件JPEG编码: ImageReader( width, height, JPEG, maxImages=2)
```

### 6.3 双WebSocket管理

```java
// 发送通道：连接 /api/ws/camera-upload
// 接收通道：连接 /api/ws/projector
// 两通道独立，发送通道连接失败不影接收通道

private void connectCameraUpload() {
    wsCameraClient = new WebSocketClient(URI.create(serverUrl + "/api/ws/camera-upload")) {
        @Override
        public void onOpen(ServerHandshake handshake) {
            Log.d(TAG, "Camera upload connected");
        }
        // onMessage: 后端可发送帧率控制指令
        // onClose: 自动重连
    };
    wsCameraClient.connect();
}

private void connectProjector() {
    // 现有的投影接收逻辑不变
}
```

### 6.4 帧发送循环

```java
// 从ImageReader拿到JPEG → Base64编码 → WebSocket发送
// 发送频率控制：每3帧发1帧（20 FPS实际处理，60 FPS采集）
// 60 FPS全发也可以，看后端处理能力

private void onFrameAvailable(byte[] jpegData, long timestamp) {
    if (frameSkipCounter++ % 3 != 0) return;  // 后端每3帧处理一次
    
    String b64 = Base64.encodeToString(jpegData, Base64.NO_WRAP);
    JSONObject msg = new JSONObject();
    msg.put("type", "camera_frame");
    msg.put("width", 2560);
    msg.put("height", 1440);
    msg.put("timestamp", timestamp);
    msg.put("data", b64);
    
    if (wsCameraClient != null && wsCameraClient.isOpen()) {
        wsCameraClient.send(msg.toString());
    }
}
```

---

## 7. 退化方案

| 场景 | 处理 |
|------|------|
| 安卓盒子未连接摄像头 | WebSocket只接收投影，不发送帧；后端降级为离线模式 |
| 摄像头断连/重新插拔 | Android CameraManager.AvailabilityCallback检测，自动重连 |
| WiFi断开 | 两端WebSocket自动重连（已有机制），环形缓冲丢弃旧帧 |
| 后端未启动 | 盒子显示"等待后端连接..."占位画面 |
| USB线松动 | 连续3帧无有效数据→后端显示"摄像头异常"并保持最后已知桌面状态 |

---

## 8. 成本估算

| 设备 | 型号 | 参考价 |
|------|------|--------|
| 安卓盒子 | X96 X10 (S928X) | ¥400-600 |
| USB摄像头 | 2K@60FPS UVC | ¥300-500 |
| 投影仪 | 当贝D5X / 小明Q3 Pro | ¥1200-2800 |
| USB延长线 | USB 3.0 有源 5m | ¥50-80 |
| HDMI线 | 1m | ¥10-20 |
| **合计** | | **¥2000-4000** |

vs 原方案（WiFi摄像头 ¥350 + 智能投影仪 ¥2000-4000 = ¥2350-4350），成本持平但架构更简洁。

---

## 9. 待决策项

| 事项 | 选项 | 推荐 |
|------|------|------|
| 帧发送频率 | 20 FPS（每3帧） / 60 FPS（每帧） | 20 FPS，够用且省带宽 |
| 盒子APP启动 | 手动 / 开机自启（已实现） | 开机自启 |
| USB摄像头安装 | 吊顶 / 独立支架 | 吊顶，与投影仪同一位置 |
| 盒子供电 | USB供电 / 独立电源 | 独立电源（盒子功耗较高） |
