# TripStar 多智能体架构详解

> 基于 HelloAgents 框架的多 Agent 协作旅行规划系统架构文档

---

## 1. 系统整体架构

```mermaid
graph TB
    subgraph Browser["🌐 浏览器"]
        UI["Vue3 前端<br/>Landing.vue / Result.vue"]
    end

    subgraph Vite["⚡ Vite Dev Server :5173"]
        Proxy["/api → proxy"]
    end

    subgraph FastAPI["🚀 FastAPI :8000"]
        POST["POST /api/trip/plan<br/>立即返回 task_id"]
        GET["GET /api/trip/status/:id<br/>轮询任务状态"]
        TaskStore[("_tasks: dict<br/>内存任务表")]
    end

    subgraph AgentLayer["🤖 多智能体协调层"]
        Planner["MultiAgentTripPlanner<br/>(单例)"]
    end

    subgraph External["🌍 外部服务"]
        LLM["LLM API<br/>MiniMax-M2.5"]
        MCP["amap-mcp-server<br/>高德地图 MCP"]
    end

    UI -->|"axios POST"| Proxy
    UI -->|"每3秒轮询"| Proxy
    Proxy --> POST
    Proxy --> GET
    POST -->|"asyncio.create_task"| TaskStore
    TaskStore --> Planner
    GET -->|"读取状态"| TaskStore
    Planner -->|"invoke / run"| LLM
    Planner -->|"MCPTool.run"| MCP
```

**说明：**
- 前端通过 Vite proxy 代理 `/api` 请求到后端，避免跨域
- 后端采用异步任务模式：`POST /plan` 立即返回 `task_id`，前端轮询 `GET /status` 获取结果
- 多 Agent 协调层是核心，内部编排 4 个专业 Agent 协作完成旅行规划
- 外部依赖两个服务：LLM API（文本生成）和高德地图 MCP Server（地理数据）

---

## 2. 多 Agent 协作时序图

```mermaid
sequenceDiagram
    autonumber
    participant FE as 🌐 前端
    participant API as 🚀 FastAPI
    participant MA as 🧠 MultiAgentPlanner
    participant A1 as 🏛️ 景点搜索Agent
    participant A2 as 🌤️ 天气查询Agent
    participant A3 as 🏨 酒店推荐Agent
    participant LLM as 🤖 LLM (MiniMax)
    participant MCP as 🗺️ 高德MCP

    FE->>API: POST /api/trip/plan {city, dates, prefs}
    API->>API: task_id = uuid()[:8]
    API-->>FE: {task_id, status: processing}
    API->>MA: asyncio.create_task(plan_trip)

    Note over MA: ═══ Step 1/4: 搜索景点 ═══
    MA->>A1: asyncio.to_thread(run, query)
    A1->>LLM: invoke(system_prompt + query)
    LLM-->>A1: [TOOL_CALL:amap:maps_text_search,keywords=历史文化,city=北京]
    A1->>A1: _parse_tool_calls() 正则解析
    A1->>MCP: MCPTool.run({maps_text_search, args})
    MCP-->>A1: POI搜索结果
    A1->>LLM: invoke(messages + 工具结果)
    LLM-->>A1: 景点摘要文本
    A1-->>MA: attraction_response

    Note over MA: ═══ Step 2/4: 查询天气 ═══
    MA->>A2: asyncio.to_thread(run, query)
    A2->>LLM: invoke(system_prompt + query)
    LLM-->>A2: [TOOL_CALL:amap:maps_weather,city=北京]
    A2->>MCP: MCPTool.run({maps_weather, city})
    MCP-->>A2: 天气预报数据
    A2->>LLM: invoke(messages + 天气数据)
    LLM-->>A2: 天气摘要
    A2-->>MA: weather_response
    MA->>MA: _build_weather_for_dates()

    Note over MA: ═══ Step 3/4: 搜索酒店 ═══
    MA->>A3: asyncio.to_thread(run, query)
    A3->>LLM: invoke + [TOOL_CALL] + MCP 调用
    A3-->>MA: hotel_response

    Note over MA: ═══ Step 4/4: 整合生成行程 ═══
    MA->>MA: _build_planner_query(景点+天气+酒店)
    MA->>LLM: invoke(PLANNER_PROMPT + 汇总, max_tokens=8192)
    LLM-->>MA: ```json { city, days, budget... } ```
    MA->>MA: _parse_response() + json_repair

    MA-->>API: TripPlan 对象
    API->>API: build_knowledge_graph()
    API->>API: _tasks[id] = completed

    FE->>API: GET /api/trip/status/{task_id}
    API-->>FE: {status: completed, result: ...}
```

**说明：**
- Step 1-3 各自调用一个专业 Agent，每个 Agent 内部经历 `LLM → 工具调用 → LLM 总结` 的 ReAct 循环
- Step 4 直接调用 LLM（不走 Agent），将前三步的结果汇总为结构化 JSON
- `asyncio.to_thread` 将同步的 `agent.run()` 放入线程池，不阻塞事件循环
- Step 4 有最多 3 次重试机制，确保 LLM 输出有效的 JSON

---

## 3. SimpleAgent 工具调用循环（ReAct 模式）

```mermaid
flowchart TD
    Start(["agent.run(query)"])
    Build["构建 messages<br/>system_prompt + 工具说明 + history + user"]
    Call["response = llm.invoke(messages)"]
    Parse{"正则匹配<br/>[TOOL_CALL:name:params]<br/>是否存在？"}
    Exec["_execute_tool_call()<br/>ToolRegistry → tool.run(params)"]
    Append["追加到 messages:<br/>① assistant: 清理后回复<br/>② user: 工具结果...请回答"]
    MaxCheck{"iteration < 3 ?"}
    Final(["返回 final_response"])
    Fallback["兜底: 再调一次 LLM"]

    Start --> Build --> Call --> Parse
    Parse -->|"是"| Exec --> Append --> MaxCheck
    MaxCheck -->|"是"| Call
    MaxCheck -->|"否"| Fallback --> Final
    Parse -->|"否 (最终回答)"| Final
```

**说明：**
- hello_agents 的 `SimpleAgent` **不使用** OpenAI 原生 function calling
- 而是通过 prompt 约定 `[TOOL_CALL:tool_name:key=value,...]` 格式，用正则解析
- 最多循环 3 次（`max_tool_iterations`），防止无限工具调用
- 如果循环耗尽仍未得到最终回答，会兜底再调一次 LLM

---

## 4. MCP 工具调用链路

```mermaid
flowchart LR
    A["SimpleAgent<br/>_execute_tool_call"] --> B["WrappedMCPTool<br/>参数重组<br/>平铺 → 嵌套"]
    B --> C["MCPTool.run()<br/>action=call_tool"]
    C --> D["MCPClient<br/>async with 上下文"]
    D --> E["StdioTransport<br/>启动子进程"]
    E --> F["uvx amap-mcp-server<br/>高德地图MCP服务"]
    F --> G["高德地图 Web API<br/>maps_text_search<br/>maps_weather"]

    G -->|"API 响应"| F -->|"MCP 协议"| E -->|"stdio"| D -->|"解析结果"| C -->|"文本"| B -->|"返回"| A
```

**说明：**
- `WrappedMCPTool` 是项目自定义的适配层，将 LLM 输出的平铺参数转为 MCPTool 期望的嵌套格式
- `MCPTool` 通过 `MCPClient` 管理与 MCP Server 的连接生命周期
- 底层通过 `StdioTransport` 启动 `uvx amap-mcp-server` 子进程，经 stdio 管道通信
- 最终调用高德地图 Web API 获取 POI 搜索、天气查询等数据

---

## 5. 四个 Agent 角色对比

```mermaid
graph LR
    subgraph Shared["共享资源"]
        LLM["🤖 HelloAgentsLLM<br/>MiniMax-M2.5 (单例)"]
        Tool["🗺️ WrappedMCPTool<br/>amap-mcp-server (单例)"]
    end

    subgraph Agents["四个专业 Agent"]
        A1["🏛️ 景点搜索专家<br/>━━━━━━━━━━<br/>工具: amap ✅<br/>输入: 城市+偏好<br/>输出: POI列表"]
        A2["🌤️ 天气查询专家<br/>━━━━━━━━━━<br/>工具: amap ✅<br/>输入: 城市名<br/>输出: 天气预报"]
        A3["🏨 酒店推荐专家<br/>━━━━━━━━━━<br/>工具: amap ✅<br/>输入: 城市+类型<br/>输出: 酒店列表"]
        A4["📋 行程规划专家<br/>━━━━━━━━━━<br/>工具: 无 ❌<br/>输入: 前3步汇总<br/>输出: JSON行程"]
    end

    LLM --- A1
    LLM --- A2
    LLM --- A3
    LLM --- A4
    Tool --- A1
    Tool --- A2
    Tool --- A3
```

**说明：**

| Agent | 角色 | 绑定工具 | 调用的 MCP 操作 | 输出 |
|-------|------|---------|----------------|------|
| 景点搜索专家 | 根据城市和偏好搜索景点 | `amap` ✅ | `maps_text_search` | POI 列表文本 |
| 天气查询专家 | 查询目的地天气预报 | `amap` ✅ | `maps_weather` | 天气预报文本 |
| 酒店推荐专家 | 搜索合适的酒店 | `amap` ✅ | `maps_text_search` | 酒店列表文本 |
| 行程规划专家 | 整合数据生成 JSON 行程 | 无 ❌ | — | 结构化 JSON |

---

## 6. 关键设计决策

### 异步任务 + 轮询（解决网关超时）
LLM 生成完整行程可能耗时数分钟，直接等待会导致 504。采用 `asyncio.create_task` 推入后台 + 前端每 3 秒轮询的模式。

### 文本格式工具调用（兼容任意 LLM）
不依赖 OpenAI function calling API，通过 prompt 约定 `[TOOL_CALL:...]` 格式 + 正则解析，兼容 MiniMax、豆包等国产模型。

### MCP 协议集成（解耦地图服务）
通过 MCP 协议与高德地图服务通信，地图服务作为独立子进程运行，与主应用解耦。

### 单例模式（避免重复初始化）
LLM 实例、Agent 实例、MCP 工具均为单例，避免每次请求重新建立连接。

### JSON 容错（应对 LLM 输出不稳定）
Step 4 有 3 次重试机制 + `json_repair` 库修复格式错误 + fallback 备用计划兜底。
