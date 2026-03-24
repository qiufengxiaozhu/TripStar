"""
知识图谱构建服务
从 TripPlan 数据中提取实体(节点)和关系(边)，生成力导向图数据
"""

from typing import Any
from ..models.schemas import TripPlan


# ============ 节点颜色配置 ============
NODE_COLORS = {
    "city":       "#4A90D9",   # 蓝色 - 城市
    "day":        "#5B8FF9",   # 浅蓝 - 天
    "attraction": "#5AD8A6",   # 绿色 - 景点
    "hotel":      "#F6BD16",   # 金色 - 酒店
    "meal":       "#E8684A",   # 珊瑚红 - 餐饮
    "weather":    "#6DC8EC",   # 天蓝 - 天气
    "budget":     "#FF9845",   # 橙色 - 预算
    "preference": "#B37FEB",   # 紫色 - 偏好
}

NODE_SIZES = {
    "city":       70,
    "day":        45,
    "attraction": 35,
    "hotel":      35,
    "meal":       25,
    "weather":    28,
    "budget":     40,
    "preference": 30,
}


def build_knowledge_graph(trip_plan: TripPlan) -> dict[str, Any]:
    """
    从 TripPlan 构建知识图谱数据

    Returns:
        {
            "nodes": [{"id", "name", "category", "symbolSize", "value", ...}],
            "edges": [{"source", "target", "label"}],
            "categories": [{"name"}]
        }
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids = set()

    # ---- 分类定义 (ECharts graph categories) ----
    categories = [
        {"name": "城市"},
        {"name": "日程"},
        {"name": "景点"},
        {"name": "酒店"},
        {"name": "餐饮"},
        {"name": "天气"},
        {"name": "预算"},
        {"name": "偏好/建议"},
    ]
    cat_map = {c["name"]: i for i, c in enumerate(categories)}

    def add_node(nid: str, name: str, category_name: str, extra_value: str = ""):
        if nid in node_ids:
            return
        node_ids.add(nid)
        cat_key = {
            "城市": "city", "日程": "day", "景点": "attraction",
            "酒店": "hotel", "餐饮": "meal", "天气": "weather",
            "预算": "budget", "偏好/建议": "preference",
        }.get(category_name, "city")
        nodes.append({
            "id": nid,
            "name": name,
            "category": cat_map.get(category_name, 0),
            "symbolSize": NODE_SIZES.get(cat_key, 30),
            "itemStyle": {"color": NODE_COLORS.get(cat_key, "#999")},
            "value": extra_value,
        })

    def add_edge(source: str, target: str, label: str = ""):
        edges.append({"source": source, "target": target, "label": label})

    # ========== 1. 城市中心节点 ==========
    city_id = f"city_{trip_plan.city}"
    add_node(city_id, trip_plan.city, "城市", f"{trip_plan.start_date} ~ {trip_plan.end_date}")

    # ========== 2. 每日节点 ==========
    for day in trip_plan.days:
        day_id = f"day_{day.day_index}"
        add_node(day_id, f"第{day.day_index + 1}天", "日程", day.date)
        add_edge(city_id, day_id, "行程")

        # ---- 景点 ----
        for i, attr in enumerate(day.attractions):
            attr_id = f"attr_{day.day_index}_{i}_{attr.name}"
            value_parts = []
            if attr.address:
                value_parts.append(attr.address)
            if attr.visit_duration:
                value_parts.append(f"游览{attr.visit_duration}分钟")
            if attr.ticket_price:
                value_parts.append(f"门票¥{attr.ticket_price}")
            add_node(attr_id, attr.name, "景点", " | ".join(value_parts))
            add_edge(day_id, attr_id, "游览")

            # 景点间顺序关系
            if i > 0:
                prev_attr = day.attractions[i - 1]
                prev_id = f"attr_{day.day_index}_{i-1}_{prev_attr.name}"
                add_edge(prev_id, attr_id, "下一站")

        # ---- 酒店 ----
        if day.hotel:
            hotel_id = f"hotel_{day.day_index}_{day.hotel.name}"
            add_node(hotel_id, day.hotel.name, "酒店",
                     f"{day.hotel.price_range} | ¥{day.hotel.estimated_cost}/晚" if day.hotel.estimated_cost else day.hotel.price_range)
            add_edge(day_id, hotel_id, "入住")

        # ---- 餐饮 ----
        for j, meal in enumerate(day.meals):
            meal_label_map = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "小吃"}
            meal_type_cn = meal_label_map.get(meal.type, meal.type)
            meal_id = f"meal_{day.day_index}_{j}_{meal.name}"
            add_node(meal_id, f"{meal_type_cn}: {meal.name}", "餐饮",
                     f"¥{meal.estimated_cost}" if meal.estimated_cost else "")
            add_edge(day_id, meal_id, meal_type_cn)

    # ========== 3. 天气节点 ==========
    for w in trip_plan.weather_info:
        w_id = f"weather_{w.date}"
        add_node(w_id, f"{w.day_weather} {w.day_temp}°C", "天气", w.date)
        # 尝试关联到对应天
        for day in trip_plan.days:
            if day.date == w.date:
                add_edge(f"day_{day.day_index}", w_id, "天气")
                break

    # ========== 4. 预算节点 ==========
    if trip_plan.budget:
        b = trip_plan.budget
        budget_id = "budget_total"
        add_node(budget_id, f"总预算 ¥{b.total}", "预算", "")
        add_edge(city_id, budget_id, "预算")

        for label, value in [
            ("景点", b.total_attractions),
            ("酒店", b.total_hotels),
            ("餐饮", b.total_meals),
            ("交通", b.total_transportation),
        ]:
            if value:
                sub_id = f"budget_{label}"
                add_node(sub_id, f"{label} ¥{value}", "预算", "")
                add_edge(budget_id, sub_id, label)

    # ========== 5. 总体建议节点 ==========
    if trip_plan.overall_suggestions:
        sug_id = "suggestion_overall"
        # 截断过长文本
        sug_text = trip_plan.overall_suggestions[:30] + "..." if len(trip_plan.overall_suggestions) > 30 else trip_plan.overall_suggestions
        add_node(sug_id, sug_text, "偏好/建议", trip_plan.overall_suggestions)
        add_edge(city_id, sug_id, "建议")

    return {
        "nodes": nodes,
        "edges": edges,
        "categories": categories,
    }
