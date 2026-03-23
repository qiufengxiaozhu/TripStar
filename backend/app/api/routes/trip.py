"""旅行规划API路由 - 异步轮询模式"""

import asyncio
import uuid
from fastapi import APIRouter, HTTPException
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse
)
from ...agents.trip_planner_agent import get_trip_planner_agent
from ...services.knowledge_graph_service import build_knowledge_graph

router = APIRouter(prefix="/trip", tags=["旅行规划"])

# 内存任务存储（单实例部署足够）
_tasks: dict = {}


@router.post(
    "/plan",
    summary="提交旅行规划任务",
    description="异步提交旅行规划请求，立即返回 task_id，通过 /trip/status/{task_id} 轮询结果"
)
async def plan_trip(request: TripRequest):
    """
    提交旅行规划任务（立即返回 task_id）
    """
    task_id = str(uuid.uuid4())[:8]

    print(f"\n{'='*60}", flush=True)
    print(f"[REQUEST] 收到旅行规划请求 (task_id={task_id}):", flush=True)
    print(f"[REQUEST]   城市: {request.city}", flush=True)
    print(f"[REQUEST]   日期: {request.start_date} - {request.end_date}", flush=True)
    print(f"[REQUEST]   天数: {request.travel_days}", flush=True)
    print(f"{'='*60}\n", flush=True)

    # 将任务状态标记为进行中
    _tasks[task_id] = {"status": "processing", "progress": "正在初始化智能体..."}

    # 启动后台任务
    asyncio.create_task(_run_trip_planning(task_id, request))

    return {"task_id": task_id, "status": "processing", "message": "任务已提交，请轮询 /api/trip/status/" + task_id}


async def _run_trip_planning(task_id: str, request: TripRequest):
    """后台执行旅行规划"""
    try:
        _tasks[task_id]["progress"] = "正在获取多智能体系统实例..."
        agent = get_trip_planner_agent()

        _tasks[task_id]["progress"] = "AI 正在规划行程，请稍候..."
        trip_plan = await agent.plan_trip(request)

        _tasks[task_id]["progress"] = "正在构建知识图谱..."
        graph_data = build_knowledge_graph(trip_plan)

        print(f"[TASK] 任务 {task_id} 完成", flush=True)

        _tasks[task_id] = {
            "status": "completed",
            "result": TripPlanResponse(
                success=True,
                message="旅行计划生成成功",
                data=trip_plan,
                graph_data=graph_data
            )
        }

    except Exception as e:
        print(f"[TASK] 任务 {task_id} 失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        _tasks[task_id] = {
            "status": "failed",
            "error": str(e)
        }


@router.get(
    "/status/{task_id}",
    summary="查询任务状态",
    description="轮询旅行规划任务的执行状态和结果"
)
async def get_task_status(task_id: str):
    """查询任务执行状态"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = _tasks[task_id]

    if task["status"] == "completed":
        result = task["result"]
        # 任务完成后清理内存
        del _tasks[task_id]
        return {
            "status": "completed",
            "result": result
        }
    elif task["status"] == "failed":
        error = task["error"]
        del _tasks[task_id]
        return {
            "status": "failed",
            "error": error
        }
    else:
        return {
            "status": "processing",
            "progress": task.get("progress", "处理中...")
        }


@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        agent = get_trip_planner_agent()
        return {
            "status": "healthy",
            "service": "trip-planner",
            "agent_name": agent.agent.name,
            "tools_count": len(agent.agent.list_tools())
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
