# Pool AR - 台球智能AR投影系统

中式八球智能AR投影训练/比赛系统。通过WiFi摄像头采集桌面视频，电脑进行视觉识别和物理计算，将进攻路线实时投影到台面，手机APP遥控操作。

## 系统架构

```
📷 WiFi摄像头 ──┐
                │ WiFi
📽️ 智能投影仪 ──┤
                ├─── 🌐 路由器 ─── 💻 电脑 (Python/FastAPI)
📱 安卓手机 ────┘
                                🖥️ NAS/软路由 → VGA → 液晶屏 (比分网页)
```

| 组件 | 说明 |
|------|------|
| 💻 电脑后端 | Windows，Python/FastAPI，视觉识别+物理计算+API服务 |
| 📷 WiFi摄像头 | 俯拍桌面，RTSP协议视频流 |
| 📽️ 智能投影仪 | Android系统，安装投影APP，显示进攻路线+TTS语音播报 |
| 📱 安卓手机 | 控制APP，模式切换/预览/校准 |
| 🖥️ 比分液晶屏 | 浏览器打开比分网页，WebSocket实时更新 |

## 核心功能

- **比赛模式** — 自动识别球色归属(纯色/花色)、实时比分、黑8胜负判定、犯规换手
- **训练模式** — 全国10档50题标准训练体系、摆球验证、自动进球判定
- **闯关模式** — 连续3次成功晋级，逐步解锁高难度关卡
- **AI学习引擎** — 从击球数据中学习桌面物理特性，越打越准（~12k参数残差修正网络）
- **语音播报** — 后端生成播报文字，投影仪TTS语音合成（15种比赛/训练场景）
- **投影路线** — 白球路径、目标球路径、推荐杆法力度、母球走位落点
- **杆速检测** — 摄像头帧间分析测量母球初速度，实时显示
- **进袋检测** — 连续帧对比+多帧确认，自动检测进球事件
- **投影校准** — 9点十字线网格校准，结果持久化
- **手机APP** — 三Tab导航(主页/进行中/设置)，摄像头预览，投影预览
- **比分网页** — 大字比分、1-15号球状态面板、训练进度显示，WebSocket实时更新

## 快速开始

### 1. 启动电脑后端

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 启动
cd backend
python main.py
```

或双击 `start_backend.bat`。

### 2. 配置摄像头

编辑 `backend/config.py`，修改 `CAMERA_RTSP_URL`：

```python
CAMERA_RTSP_URL = "rtsp://admin:password@192.168.1.100/stream1"
```

### 3. 安装手机APP

用 Android Studio 打开 `phone-app/`，Build → Build APK，安装到手机。

### 4. 安装投影仪APP

用 Android Studio 打开 `projector-app/`，Build → Build APK，安装到投影仪。

### 5. 查看比分

浏览器打开 `http://电脑IP:8000/scoreboard`（NAS或软路由上效果更佳）。

## 操作说明

1. 打开手机APP，自动发现后端或手动输入IP
2. 点击"启动系统"
3. 选择模式：
   - **比赛模式** — 输入选手姓名，开始对局
   - **训练模式** — 选择1-10档难度，按投影提示摆球击球
   - **闯关模式** — 挑战更高难度
4. 投影仪自动显示推荐进攻路线和提示

## 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | Python 3.11+ / FastAPI / Uvicorn |
| 视觉处理 | OpenCV 4.x / NumPy |
| AI框架 | PyTorch 2.x（可选，无PyTorch时自动降级）|
| 图像渲染 | Pillow |
| 通信 | REST API / WebSocket / UDP广播 |
| 手机APP | Java / Android SDK 34 / Gson / Java-WebSocket |
| 投影仪APP | Java / Android SDK 34 / Gson / Java-WebSocket / TTS |

## 项目结构

```
backend/
├── main.py                 # 系统主入口
├── config.py               # 全局配置
├── api/                    # REST API + WebSocket
├── camera/                 # RTSP摄像头
├── vision/                 # 视觉识别（桌/球/袋口/杆速）
├── physics/                # 物理引擎
├── game/                   # 比赛/训练/播报
├── learning/               # AI学习引擎
├── renderer/               # 投影渲染
└── web/                    # 比分网页

phone-app/                  # 安卓手机控制APP
projector-app/              # 安卓投影仪APP
```

## 详细文档

参见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。
