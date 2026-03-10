# 旅途星辰 (TripStar) - AI 旅行智能体

> **基于 HelloAgents 框架打造的多智能体协作文旅规划平台**
<img width="1418" height="619" alt="PixPin_2026-03-11_00-38-31" src="https://github.com/user-attachments/assets/43d55fdf-beb2-47ea-b4a0-219613524776" />
<p align="center">
  <img src="https://img.shields.io/badge/license-GPL--2.0-orange">
  <img src="https://img.shields.io/badge/version-v0.1.0-green">
  <img src="https://img.shields.io/badge/Docker-Build-blue?logo=docker">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg">
  <img src="https://img.shields.io/badge/vue-3.x-brightgreen.svg">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-teal.svg">
</p>

> [!IMPORTANT]
> 
> 可直接魔撘平台使用已部署的项目：[旅途星辰 (TripStar) - AI 旅行智能体](https://modelscope.cn/studios/lcclxy/Journey-to-the-China)
> 
> 其中包括：旅行计划、景点地图、预算明细、每日行程：行程描述、交通方式、住宿推荐、景点安排（地址、游览时长、景点描述）、餐饮安排、天气信息、知识图谱可视化、沉浸式伴游 AI 问答......

## 项目简介

**旅途星辰 (TripStar)** 是一个创新的 AI 文旅智能体应用，基于 HelloAgents 框架打造的多智能体协作文旅规划平台，旨在解决用户在规划旅行时面临的“信息过载”和“决策疲劳”问题。

有别于传统的旅游攻略网站，本项目采用了基于 **大语言模型 (LLM)** 和 **多智能体 (Multi-Agent)** 协作架构的创新模式。它能像一位经验丰富的人类旅行管家一样，全面考虑用户的个性化需求（偏好设置：交通方式、住宿风格、旅行兴趣、特殊需求等），自动搜索旅行信息、查询当地天气、精选酒店并规划最优景点路线，最终输出一份结构化、可视化、可交互的高定旅行路书，**快速完成旅游攻略**。

### 核心亮点

* **多智能体协作协同**: 采用分工明确的多个 Agent（如景点规划师、天气预报员、酒店推荐专家），通过工作流 (Workflow) 协同完成复杂的旅行规划任务。
* **并发执行优化**: 将互不依赖的子任务（如搜索景点、查询天气、精选酒店）利用 `asyncio.gather` 进行并发执行，将响应时间从串行的 $T_1+T_2+T_3$ 大幅缩短至 $\max(T_1, T_2, T_3)$。
* **知识图谱可视化**: 将生成的行程数据实时转换为节点关系图（基于 ECharts的力导向图），直观展示“城市-天数-行程节点-预算”的空间结构。
* **沉浸式伴游 AI 问答**: 在生成报告后，提供悬浮式 AI 问答窗口。AI 拥有完整行程的上下文记忆，用户可随时针对行程细节（如票价、餐饮）进行追问。
* **MCP 工具调用能力**: 深度集成 Model Context Protocol (MCP)，通过 `uvx amap-mcp-server` 实时调用高德地图 API，获取精准真实的地理和 POI 数据。
* **奢华暗黑玻璃拟物风**: 全新设计的暗黑系玻璃拟物化 (Dark Luxury Glassmorphism) 界面，提供极具沉浸感的高级视觉体验。
---
> 举个例子要去中国杭州玩耍，只需要填写地点、日期、偏好设置，即可等待行程规划的结果
<img width="2733" height="1206" alt="PixPin_2026-03-11_00-36-25" src="https://github.com/user-attachments/assets/460dbe44-20ac-432f-a656-7ae707af7a78" />


## 系统架构

本项目采用标准的前后端分离架构，分为前端 Vue 交互层、后端 FastAPI 服务层和 LLM/Agents 的智能推理层。

```mermaid
graph TD
    subgraph G1 ["前端交互视图"]
        A1["参数输入 Home.vue"]
        A2["沉浸加载动画"]
        A3["高定路书 Result.vue"]
        A4["知识图谱侧边栏"]
        A5["AI 旅行智能体浮窗"]
    end

    subgraph G2 ["后端网关"]
        B1["异步轮询机制 <br/> POST/plan & GET/status"]
        B2["上下文伴游问答<br/>POST/chat/ask"]
    end

    subgraph G3 ["多智能体协同引擎"]
        C1["旅程总控 Agent"]
        C2["景点规划 Agent"]
        C3["天气预报 Agent"]
        C4["酒店推荐 Agent"]
    end

    subgraph G4 ["服务层"]
        D1["LLM模型API <br/> qwen/intern-latest"]
        D2["高德 MCP Server <br/> 地理编码/POI搜索"]
        D3["天气/时间检索工具"]
    end

    %% 交互连线
    A1 --> B1
    A3 <--> B1
    A5 <--> B2

    B1 --> C1
    B2 --> D1

    C1 --> C2
    C1 --> C3
    C1 --> C4

    C2 <--> D2
    C3 <--> D3
    C4 <--> D2

```

---

## 核心功能与工作流

### 1. 异步轮询任务系统 (解决网关超时)

针对 LLM 生成超长文本易导致 504 Gateway Timeout 的痛点，重构了后端的任务调度机制。

* **`POST /api/trip/plan`**: 立即返回 `task_id`，将长达数分钟的推理任务推入后台 `asyncio.create_task`。
* **`GET /api/trip/status/{task_id}`**: 前端每 3 秒发起一次轻量请求，实时获取当前处理进度（如"🔍 正在搜索景点..."），直至状态变为 `completed`。

### 2. 多智能体架构 (Agentic Workflow)

主控 Agent 接收到用户自然语言指令后，基于 React 模式拆解任务：

1. **并发启动**: 景点规划师调用地图工具寻找适宜 POI；天气管家查询目标日期的气候状况；机酒专员根据预算寻找合适落脚点。
2. **路线编排**: 主控 Agent 收集三方数据，进行统筹优化，计算两两景点间的距离和最优游玩顺序，避免行程折返跑。
3. **结果聚合**: 最终输出包含预算明细、逐日行程、防坑指南等详细参数的结构化 JSON。

### 3. 数据驱动的动态组件渲染

前端不再是写死的静态展示，而是通过响应式变量读取 JSON 数据：

* **高德地图 JS API 2.0 组件**: 动态读取 POI 经纬度，绘制连线与标记。
* **ECharts 知识图谱组件**: 将树状的旅行层级转化为关系网络（图数据库雏形）。

---

## 快速部署与运行指北

### 环境准备

* Python 3.10+
* Node.js 18+
* 大模型 API Key（推荐使用兼容 OpenAI 格式的服务商，如阿里云百炼、书生浦语）
* 高德地图 Web SDK API Key 和 Web 服务 API Key (并在配置中启用 **安全密钥 JSCode**)（[高德api](https://lbs.amap.com/)）
* 图片抓取api（[Unsplash API](https://unsplash.com/developers)）
* 系统已安装 `uv` 包管理器（用于 MCP 环境隔离）。

### 1. 后端启动

```bash
# 进入后端主目录
cd backend

# 安装项目依赖包
pip install -r requirements.txt

# 复制配置文件并填入相应的 API KEY
cp .env.example .env
# [必填] LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID
# [必填] AMAP_API_KEY (高德地图web服务API)
# [必填] Unsplash API Credentials（创建应用后的key）

# 启动 FastAPI (推荐通过 uvicorn)
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

API 启动后，您可以访问 `http://localhost:8000/docs` 查看 Swagger 互动文档。

### 2. 前端启动

```bash
# 进入前端主目录
cd frontend

# 使用 npm (或 pnpm/yarn) 安装依赖
npm install

# 配置前端环境变量，创建 .env 文件
# 注意：VITE_AMAP_WEB_JS_KEY 必须是 Web前端 JS API 类型的 key
# 另外，由于 JS API 2.0 政策要求，**还需要在 index.html 注入你的安全密钥(securityJsCode)**

# 启动 Vite 开发服务器
npm run dev
```

### 3. 生产环境 Docker / 魔撘社区快速部署

本项目已经适配 **魔搭社区 (ModelScope)** 等云端编程式创空间，只需要将前后端env文件配置完成后，同时将ms_deploy.json和Dockerfile里面的key进行覆写，最后一步将整个文件放在魔撘平台创空间即可部署自己的服务啦。

1. `Dockerfile`: 定义了由 Node 构建静态文件、Python 挂载启动的全栈二阶段构建镜像过程。已将 `uv` 和 `amap-mcp-server` 前置缓冲避免由于运行时下载造成的超时。
2. `start.sh`: `gunicorn` + `uvicorn worker` 启动配置，推荐单 worker 运行以此避开异步轮询缓存击穿问题。
3. 部署时，仅需将全部代码推入魔搭空间，配置同名环境变量参数，系统即可全自动化接管。

---

## 目录结构与关键代码导读

```text
helloagents-trip-planner-new/
├── backend/                       # Python FastAPI 后端
│   ├── app/
│   │   ├── api/routes/            # 核心路由 (trip.py, chat.py)
│   │   ├── agents/                # 多智能体定义与编排 (trip_planner_agent.py 并发核心)
│   │   ├── services/              # 业务逻辑封装 (包括 amap_service MCP调用逻辑)
│   │   └── models/                # Pydantic 类型定义
│   └── .env                       # LLM 及系统环境变量载体
│
├── frontend/                      # Vue 3 互动前端
│   ├── src/
│   │   ├── views/                 # 主路由视图 (Home.vue 表单输入; Result.vue 路书展示)
│   │   ├── components/            # 独立复用的 UI / 背景组件
│   │   └── services/              # Axois 异步轮询及配置重试逻辑 (api.ts)
│   ├── index.html                 # 入口挂载及高德地图 SecurityKey 预设
│   └── package.json
│
├── ms_deploy.json                 # 魔搭创空间专属容器定义描述符
├── Dockerfile                     # 通用生产发布容器脚本
└── README.md
```

> 下面是部分运行结果，丰富的功能探索ing，欢迎大家提issues

<img width="500" height="1818" alt="旅行计划_杭州_1772887217932" src="https://github.com/user-attachments/assets/ced55dae-e03e-433a-af9d-9f3c26d34563" />

## 后续可扩展方向 (Roadmap)

1. **真实环境检索强化**: 当前依赖模型自身基础数据的景点信息，偶尔会存在模型臆想的情况。后续可增加专用的搜索引擎工具流（Tavily/SearXNG）。
2. **知识记忆库 (Zep)**: 虽然现在前端能将整段 JSON 返回给大语言模型进行 AI 答疑，但长对话将快速消耗 Token。可引入 **向量数据库Zep** 管理该应用中长期对话图景。
3. **多人拼团协同规划**: 未来开发实时 Websocket 机制，允许多个终端用户共同在大屏幕端划拨、删减目标行程节点。
