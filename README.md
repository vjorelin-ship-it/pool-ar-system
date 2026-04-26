# 台球智能AR投影系统

中式八球台球智能AR投影系统，通过WiFi摄像头获取桌面视频，使用电脑进行视觉识别和物理计算，
通过智能投影仪将进攻路线投射到桌面上，通过安卓手机APP进行控制。

## 系统组成

| 组件 | 说明 |
|------|------|
| 💻 电脑后端 | Windows电脑，运行Python程序，做视觉识别和物理计算 |
| 📷 WiFi摄像头 | 拍摄台球桌面，RTSP协议传输 |
| 📽️ 智能投影仪 | 安卓系统，安装投影APP，显示进攻路线 |
| 📱 安卓手机APP | 控制系统启动/停止/模式切换 |
| 🖥️ 比分液晶屏 | NAS或软路由浏览器打开比分网页，VGA输出 |

## 快速开始

### 1. 启动电脑后端

1. 安装 Python 3.11+ (https://www.python.org/downloads/)
2. 双击 `start_backend.bat`
3. 第一次运行会自动安装依赖

### 2. 配置摄像头

编辑 `backend/config.py`，修改 `CAMERA_RTSP_URL` 为你的WiFi摄像头地址：

```python
CAMERA_RTSP_URL = "rtsp://192.168.1.100:554/stream1"
```

### 3. 安装手机APP

- 用Android Studio打开 `phone-app/` 目录
- 构建APK：Build → Build Bundle(s) / APK(s) → Build APK
- 将生成的APK复制到手机安装

### 4. 安装投影仪APP

- 用Android Studio打开 `projector-app/` 目录
- 构建APK
- 用U盘复制到投影仪安装
- 安装后打开一次，之后开机自动启动

### 5. 比分显示屏

NAS或软路由打开浏览器，访问：
```
http://电脑IP:8000/scoreboard
```
全屏显示即可。

## 操作说明

1. 打开手机APP，自动搜索到后端电脑
2. 点击"启动系统"
3. 选择模式：
   - **比赛模式**：自动推荐最佳进攻路线，记录比分
   - **训练模式**：选择1-10档难度，系统出题
   - **闯关模式**：连续成功3次过关
4. 投影仪自动显示进攻路线

## 训练模式

10档难度等级：

| 档位 | 难度 | 说明 |
|------|------|------|
| 1 | 入门 | 直线进球 |
| 2 | 简单 | 小角度进球 |
| 3 | 初级 | 中等角度 |
| 4 | 中级 | 大角度 |
| 5 | 进阶级 | 高杆/低杆走位 |
| 6 | 挑战 | 加塞（侧旋） |
| 7 | 困难 | 翻袋（吃一库） |
| 8 | 高阶 | 两库翻袋 |
| 9 | 专家 | 组合球 |
| 10 | 大师 | 综合高级技巧 |

## 技术栈

- **Python 3.11+**: FastAPI, OpenCV, NumPy, Pillow
- **Android**: Java, WebSocket, Gson
- **通信**: REST API, WebSocket, UDP广播发现

## 文件结构

```
backend/
├── main.py                 # 主程序入口
├── config.py               # 配置
├── camera/                 # 摄像头模块
├── vision/                 # 视觉识别
├── physics/                # 物理引擎
├── game/                   # 比赛/训练逻辑
├── api/                    # API和WebSocket
├── renderer/               # 投影渲染
└── web/                    # 比分网页

phone-app/                  # 安卓手机APP
projector-app/              # 安卓投影仪APP
```
