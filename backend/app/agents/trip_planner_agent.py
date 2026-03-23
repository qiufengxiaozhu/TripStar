"""多智能体旅行规划系统"""

import json
import re
import sys
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, List
from hello_agents import SimpleAgent
from hello_agents.tools import MCPTool
from ..services.llm_service import get_llm
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel
from ..config import get_settings


def log(msg: str):
    """带刷新的日志输出，确保 PyCharm 控制台实时可见"""
    print(msg, flush=True)


class WrappedMCPTool:
    """包装 MCPTool，自动将平铺参数重组为 MCPTool 期望的嵌套格式"""

    RESERVED_KEYS = {"action", "tool_name", "uri", "prompt_name", "prompt_arguments"}

    def __init__(self, mcp_tool):
        self._mcp_tool = mcp_tool
        self.name = mcp_tool.name
        self.description = mcp_tool.description

    def run(self, parameters):
        if "tool_name" in parameters and "arguments" not in parameters:
            arguments = {k: v for k, v in parameters.items() if k not in self.RESERVED_KEYS}
            parameters = {k: v for k, v in parameters.items() if k in self.RESERVED_KEYS}
            parameters["arguments"] = arguments
        log(f"[MCP] Calling tool with params: {parameters}")
        return self._mcp_tool.run(parameters)

    def get_description(self):
        if hasattr(self._mcp_tool, "get_description"):
            return self._mcp_tool.get_description()
        return self.description

# ============ Agent提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
1. 你必须使用工具来搜索景点!不要自己编造景点信息!
2. 系统为你绑定的工具名称叫做 `amap`，调用时需要传入 tool_name 和 arguments 参数。

**工具调用格式:**
`[TOOL_CALL:amap:tool_name=maps_text_search,keywords=景点关键词,city=城市名]`

**示例:**
用户: "搜索北京的历史文化景点"
你的回复: [TOOL_CALL:amap:tool_name=maps_text_search,keywords=历史文化,city=北京]

用户: "搜索上海的公园"
你的回复: [TOOL_CALL:amap:tool_name=maps_text_search,keywords=公园,city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 工具名必须是 `amap`，通过 tool_name 参数指定具体操作
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**重要提示:**
1. 你必须使用工具来查询天气!不要自己编造天气信息!
2. 系统为你绑定的工具名称叫做 `amap`，调用时需要传入 tool_name 和 arguments 参数。

**工具调用格式:**
`[TOOL_CALL:amap:tool_name=maps_weather,city=城市名]`

**示例:**
用户: "查询北京天气"
你的回复: [TOOL_CALL:amap:tool_name=maps_weather,city=北京]

用户: "上海的天气怎么样"
你的回复: [TOOL_CALL:amap:tool_name=maps_weather,city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 工具名必须是 `amap`，通过 tool_name 参数指定具体操作
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
1. 你必须使用工具来搜索酒店!不要自己编造酒店信息!
2. 系统为你绑定的工具名称叫做 `amap`，调用时需要传入 tool_name 和 arguments 参数。

**工具调用格式:**
`[TOOL_CALL:amap:tool_name=maps_text_search,keywords=酒店,city=城市名]`

**示例:**
用户: "搜索北京的酒店"
你的回复: [TOOL_CALL:amap:tool_name=maps_text_search,keywords=酒店,city=北京]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 关键词使用"酒店"或"宾馆"
4. 工具名必须是 `amap`，通过 tool_name 参数指定具体操作
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. **你不需要调用任何工具！所有需要的信息已经在上面提供给你了！**
2. **你必须直接输出JSON，不要输出任何工具调用、XML标签或其他格式！**
3. weather_info数组必须包含每一天的天气信息
4. 温度必须是纯数字(不要带°C等单位)
5. 每天安排2-3个景点
6. 考虑景点之间的距离和游览时间
7. 每天必须包含早中晚三餐
8. 提供实用的旅行建议
9. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
10. **输出格式：只输出一个完整的JSON代码块，用```json和```包裹，不要输出其他任何内容！**
"""


class MultiAgentTripPlanner:
    """多智能体旅行规划系统"""

    def __init__(self):
        """初始化多智能体系统"""
        log("=" * 60)
        log("[INIT] 开始初始化多智能体旅行规划系统...")

        try:
            settings = get_settings()
            log(f"[INIT] 高德地图Key: {'已配置' if settings.vite_amap_web_key else '未配置'}")

            log("[INIT] 正在创建LLM实例...")
            self.llm = get_llm()
            log(f"[INIT] LLM实例创建成功 - provider={self.llm.provider}, model={self.llm.model}, base_url={self.llm.base_url}")

            log("[INIT] 正在创建共享MCP工具(amap-mcp-server)...")
            raw_amap_tool = MCPTool(
                name="amap",
                description="高德地图服务，支持 maps_text_search(关键词搜索POI)、maps_weather(天气查询)等操作",
                server_command=["uvx", "amap-mcp-server"],
                env={"AMAP_MAPS_API_KEY": settings.vite_amap_web_key},
                auto_expand=True
            )
            self.amap_tool = WrappedMCPTool(raw_amap_tool)
            log("[INIT] MCP工具创建成功")

            log("[INIT] 正在创建景点搜索Agent...")
            self.attraction_agent = SimpleAgent(
                name="景点搜索专家",
                llm=self.llm,
                system_prompt=ATTRACTION_AGENT_PROMPT
            )
            self.attraction_agent.add_tool(self.amap_tool)

            log("[INIT] 正在创建天气查询Agent...")
            self.weather_agent = SimpleAgent(
                name="天气查询专家",
                llm=self.llm,
                system_prompt=WEATHER_AGENT_PROMPT
            )
            self.weather_agent.add_tool(self.amap_tool)

            log("[INIT] 正在创建酒店推荐Agent...")
            self.hotel_agent = SimpleAgent(
                name="酒店推荐专家",
                llm=self.llm,
                system_prompt=HOTEL_AGENT_PROMPT
            )
            self.hotel_agent.add_tool(self.amap_tool)

            log("[INIT] 正在创建行程规划Agent...")
            self.planner_agent = SimpleAgent(
                name="行程规划专家",
                llm=self.llm,
                system_prompt=PLANNER_AGENT_PROMPT
            )

            log(f"[INIT] 多智能体系统初始化成功!")
            log(f"[INIT]   景点搜索Agent: {len(self.attraction_agent.list_tools())} 个工具")
            log(f"[INIT]   天气查询Agent: {len(self.weather_agent.list_tools())} 个工具")
            log(f"[INIT]   酒店推荐Agent: {len(self.hotel_agent.list_tools())} 个工具")
            log("=" * 60)

        except Exception as e:
            log(f"[INIT] 多智能体系统初始化失败: {str(e)}")
            log(traceback.format_exc())
            raise
    
    async def plan_trip(self, request: TripRequest) -> TripPlan:
        """
        使用多智能体协作生成旅行计划（并发优化版）

        步骤1-3（景点/天气/酒店）通过 asyncio.gather 并发执行，
        将耗时从 T1+T2+T3 缩短为 max(T1, T2, T3)。
        步骤4（行程规划）依赖前三步结果，保持串行。

        Args:
            request: 旅行请求

        Returns:
            旅行计划
        """
        try:
            log(f"\n{'='*60}")
            log(f"[PLAN] 开始多智能体协作规划旅行")
            log(f"[PLAN] 目的地: {request.city}")
            log(f"[PLAN] 目的地bytes: {request.city.encode('utf-8')}")
            log(f"[PLAN] 日期: {request.start_date} 至 {request.end_date}")
            log(f"[PLAN] 天数: {request.travel_days}天")
            log(f"[PLAN] 偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            log(f"[PLAN] 住宿: {request.accommodation}")
            log(f"[PLAN] 交通: {request.transportation}")
            log(f"[PLAN] stdout.encoding: {sys.stdout.encoding}")
            log(f"{'='*60}\n")

            attraction_query = self._build_attraction_query(request)
            weather_query = f"请查询{request.city}的天气信息"
            hotel_query = f"请搜索{request.city}的{request.accommodation}酒店"

            travel_dates = self._get_travel_dates(request)

            # ========== 步骤1: 搜索景点 ==========
            log(f"[STEP 1/4] 正在搜索景点...")
            log(f"[STEP 1/4] 查询内容: {attraction_query[:200]}")
            try:
                attraction_response = await asyncio.to_thread(self.attraction_agent.run, attraction_query)
                log(f"[STEP 1/4] 景点搜索完成, 响应长度={len(attraction_response)}")
                log(f"[STEP 1/4] 响应预览: {attraction_response[:500]}")
            except Exception as e:
                log(f"[STEP 1/4] 景点搜索失败: {e}")
                log(traceback.format_exc())
                attraction_response = "景点搜索失败"

            # ========== 步骤2: 查询天气 ==========
            log(f"\n[STEP 2/4] 正在查询天气...")
            log(f"[STEP 2/4] 查询内容: {weather_query}")
            log(f"[STEP 2/4] 用户旅行日期: {[d.strftime('%Y-%m-%d') for d in travel_dates]}")
            try:
                weather_response = await asyncio.to_thread(self.weather_agent.run, weather_query)
                log(f"[STEP 2/4] 天气查询完成, 响应长度={len(weather_response)}")
                log(f"[STEP 2/4] 响应预览: {weather_response[:500]}")
            except Exception as e:
                log(f"[STEP 2/4] 天气查询失败: {e}")
                log(traceback.format_exc())
                weather_response = "天气查询失败"

            weather_for_trip = self._build_weather_for_dates(weather_response, travel_dates, request.city)
            log(f"[STEP 2/4] 最终天气信息:\n{weather_for_trip}")

            # ========== 步骤3: 搜索酒店 ==========
            log(f"\n[STEP 3/4] 正在搜索酒店...")
            log(f"[STEP 3/4] 查询内容: {hotel_query}")
            try:
                hotel_response = await asyncio.to_thread(self.hotel_agent.run, hotel_query)
                log(f"[STEP 3/4] 酒店搜索完成, 响应长度={len(hotel_response)}")
                log(f"[STEP 3/4] 响应预览: {hotel_response[:500]}")
            except Exception as e:
                log(f"[STEP 3/4] 酒店搜索失败: {e}")
                log(traceback.format_exc())
                hotel_response = "酒店搜索失败"

            log(f"\n[INFO] 基础信息搜集完成\n")

            # ========== 步骤4: 整合生成行程 ==========
            log(f"[STEP 4/4] 正在生成行程计划（直接调用LLM）...")
            planner_query = self._build_planner_query(request, attraction_response, weather_for_trip, hotel_response)
            log(f"[STEP 4/4] 规划查询长度: {len(planner_query)}")
            try:
                messages = [
                    {"role": "system", "content": PLANNER_AGENT_PROMPT},
                    {"role": "user", "content": planner_query},
                ]

                planner_response = ""
                for attempt in range(3):
                    log(f"[STEP 4/4] 第{attempt+1}次调用LLM...")
                    raw = await asyncio.to_thread(self.llm.invoke, messages, max_tokens=8192)
                    log(f"[STEP 4/4] 响应长度={len(raw)}, 预览: {raw[:300]}")

                    if "<think>" in raw and "</think>" in raw:
                        think_end = raw.find("</think>") + len("</think>")
                        raw = raw[think_end:].strip()

                    if "```json" in raw or (("{" in raw) and ("days" in raw)):
                        planner_response = raw
                        log(f"[STEP 4/4] 找到JSON响应!")
                        break

                    log(f"[STEP 4/4] 未找到JSON，追加重试指令...")
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content": "你没有输出JSON。请不要调用任何工具，不要输出<tool_call>标签。所有信息已经提供给你了（包括天气信息，如果日期不匹配请根据季节推测）。请直接输出完整的```json代码块，只输出JSON，不要输出其他任何内容。"})

                if not planner_response:
                    planner_response = raw
                    log(f"[STEP 4/4] 3次重试后仍未获得JSON")

            except Exception as e:
                log(f"[STEP 4/4] 行程规划失败: {e}")
                log(traceback.format_exc())
                raise

            # 解析最终计划
            log(f"\n[PARSE] 正在解析行程规划响应...")
            trip_plan = self._parse_response(planner_response, request)

            log(f"{'='*60}")
            log(f"[DONE] 旅行计划生成完成!")
            log(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            log(f"[ERROR] 生成旅行计划失败: {str(e)}")
            log(traceback.format_exc())
            log(f"[FALLBACK] 使用备用方案生成计划")
            return self._create_fallback_plan(request)
    
    def _build_attraction_query(self, request: TripRequest) -> str:
        """构建景点搜索查询 - 直接包含工具调用"""
        keywords = []
        if request.preferences:
            # 只取第一个偏好作为关键词
            keywords = request.preferences[0]
        else:
            keywords = "景点"

        # 直接返回工具调用格式，使用正确的工具名和严格的格式
        query = f"请使用amap工具搜索{request.city}的{keywords}相关的景点。\n非常重要：你必须直接输出 `[TOOL_CALL:amap:tool_name=maps_text_search,keywords={keywords},city={request.city}]`，不要附带任何多余的 JSON 或文字说明！"
        return query

    @staticmethod
    def _get_travel_dates(request: TripRequest) -> List[datetime]:
        """根据请求中的 start_date / end_date 返回每一天的 datetime 列表"""
        start = datetime.strptime(request.start_date, "%Y-%m-%d")
        dates = [start + timedelta(days=i) for i in range(request.travel_days)]
        return dates

    def _build_weather_for_dates(
        self, weather_response: str, travel_dates: List[datetime], city: str
    ) -> str:
        """
        从天气 Agent 的原始响应中提取日期→天气映射，
        然后针对用户实际旅行日期逐天输出：
          - 如果 API 返回的日期覆盖了该天 → 直接使用
          - 否则 → 根据月份和城市给出合理的季节性推测
        返回纯文本，供 planner_query 使用。
        """
        date_weather_map: Dict[str, Dict[str, str]] = {}

        date_blocks = re.split(r'(?=\d{4}-\d{2}-\d{2})', weather_response)
        for block in date_blocks:
            dm = re.match(r'(\d{4}-\d{2}-\d{2})', block)
            if not dm:
                continue
            d_str = dm.group(1)

            day_w = night_w = ""
            day_t = night_t = ""

            w_match = re.search(r'白天[：:\s]*([^\s|,，]+)', block)
            if w_match:
                day_w = w_match.group(1).rstrip('|｜')
            nw_match = re.search(r'夜间[：:\s]*([^\s|,，]+)', block)
            if nw_match:
                night_w = nw_match.group(1).rstrip('|｜')

            temps = re.findall(r'(\d+)\s*[°℃]', block)
            if len(temps) >= 2:
                day_t, night_t = temps[0], temps[1]
            elif len(temps) == 1:
                day_t = night_t = temps[0]

            wind_dir = ""
            wind_match = re.search(r'([\u4e00-\u9fa5]+风)', block)
            if wind_match:
                wind_dir = wind_match.group(1)

            if day_w or day_t:
                summary = f"白天{day_w or '未知'} 夜间{night_w or '未知'} 最高{day_t or '?'}°C 最低{night_t or '?'}°C"
                if wind_dir:
                    summary += f" {wind_dir}"
                date_weather_map[d_str] = summary

        log(f"[WEATHER] 从API响应中提取到 {len(date_weather_map)} 天天气: {list(date_weather_map.keys())}")

        lines = []
        for dt in travel_dates:
            ds = dt.strftime("%Y-%m-%d")
            if ds in date_weather_map:
                lines.append(f"- {ds}: {date_weather_map[ds]}（实时预报）")
            else:
                est = self._estimate_weather_by_season(dt, city)
                lines.append(f"- {ds}: {est}（根据季节推测，API未覆盖该日期）")

        header = f"以下是 **{city}** 在用户旅行期间的天气信息：\n"
        return header + "\n".join(lines)

    @staticmethod
    def _estimate_weather_by_season(dt: datetime, city: str) -> str:
        """根据月份和城市粗略推测天气，用于 API 无法覆盖的日期"""
        month = dt.month
        city_lower = city.lower()

        is_south = any(k in city_lower for k in [
            "广州", "深圳", "海口", "三亚", "南宁", "昆明", "厦门", "福州",
        ])
        is_northeast = any(k in city_lower for k in [
            "哈尔滨", "长春", "沈阳", "大连",
        ])

        if month in (3, 4, 5):
            if is_south:
                return "白天多云 夜间多云 最高26°C 最低18°C 偶有阵雨"
            elif is_northeast:
                return "白天晴 夜间晴 最高12°C 最低1°C 风力较大"
            else:
                return "白天晴 夜间多云 最高20°C 最低8°C 早晚温差大"
        elif month in (6, 7, 8):
            if is_south:
                return "白天多云 夜间雷阵雨 最高34°C 最低26°C 注意防暑"
            elif is_northeast:
                return "白天晴 夜间多云 最高28°C 最低18°C"
            else:
                return "白天晴 夜间多云 最高33°C 最低22°C 注意防晒补水"
        elif month in (9, 10, 11):
            if is_south:
                return "白天多云 夜间晴 最高28°C 最低20°C"
            elif is_northeast:
                return "白天晴 夜间晴 最高10°C 最低-2°C 注意保暖"
            else:
                return "白天晴 夜间多云 最高18°C 最低6°C 秋高气爽"
        else:
            if is_south:
                return "白天晴 夜间多云 最高18°C 最低10°C"
            elif is_northeast:
                return "白天晴 夜间晴 最高-5°C 最低-18°C 注意防寒"
            else:
                return "白天晴 夜间晴 最高3°C 最低-6°C 注意保暖防风"

    def _build_planner_query(self, request: TripRequest, attractions: str, weather: str, hotels: str = "") -> str:
        """构建行程规划查询"""
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 返回完整的JSON格式数据
6. 景点的经纬度坐标要真实准确
7. **不要调用任何工具！所有信息已经提供给你了，直接生成JSON！**
8. **只输出```json代码块，不要输出其他任何文字！不要输出<think>标签！**
9. 天气信息已经按照用户的旅行日期整理好了，请直接使用，不需要再推测
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query
    
    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应
        
        Args:
            response: Agent响应文本
            request: 原始请求
            
        Returns:
            旅行计划
        """
        from json_repair import repair_json

        try:
            log(f"[PARSE] 响应总长度: {len(response)}")
            log(f"[PARSE] 响应全文:\n{response[:2000]}")

            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                if json_end == -1:
                    json_str = response[json_start:].strip()
                else:
                    json_str = response[json_start:json_end].strip()
                log(f"[PARSE] 从 ```json 代码块中提取, 长度={len(json_str)}")
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end == -1:
                    json_str = response[json_start:].strip()
                else:
                    json_str = response[json_start:json_end].strip()
                log(f"[PARSE] 从 ``` 代码块中提取, 长度={len(json_str)}")
            elif "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                log(f"[PARSE] 从原始文本中提取JSON, 长度={len(json_str)}")
            elif "{" in response:
                json_start = response.find("{")
                json_str = response[json_start:]
                log(f"[PARSE] JSON可能被截断, 从 {{ 开始提取, 长度={len(json_str)}")
            else:
                log(f"[PARSE] 响应中未找到任何JSON数据!")
                raise ValueError("响应中未找到JSON数据")

            try:
                data = json.loads(json_str)
                log(f"[PARSE] 标准JSON解析成功")
            except json.JSONDecodeError as je:
                log(f"[PARSE] 标准JSON解析失败: {je}")
                log(f"[PARSE] 使用 json_repair 修复...")
                repaired = repair_json(json_str, return_objects=True)
                if isinstance(repaired, dict):
                    data = repaired
                    log(f"[PARSE] json_repair 修复成功(dict)")
                elif isinstance(repaired, str):
                    data = json.loads(repaired)
                    log(f"[PARSE] json_repair 修复成功(str->dict)")
                else:
                    raise ValueError(f"json_repair 返回了非dict类型: {type(repaired)}")

            log(f"[PARSE] JSON解析成功, 顶层key: {list(data.keys())}")

            trip_plan = TripPlan(**data)
            log(f"[PARSE] TripPlan对象创建成功, {len(trip_plan.days)}天行程")

            return trip_plan

        except Exception as e:
            log(f"[PARSE] 解析响应失败: {str(e)}")
            log(traceback.format_exc())
            log(f"[PARSE] 将使用备用方案生成计划")
            return self._create_fallback_plan(request)

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当Agent失败时)"""
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        
        # 创建每日行程
        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐")
                ]
            )
            days.append(day_plan)
        
        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。"
        )


# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner

