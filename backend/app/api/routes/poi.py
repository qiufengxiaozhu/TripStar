"""POI相关API路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from ...services.amap_service import get_amap_service
from ...services.unsplash_service import get_unsplash_service

router = APIRouter(prefix="/poi", tags=["POI"])


class POIDetailResponse(BaseModel):
    """POI详情响应"""
    success: bool
    message: str
    data: Optional[dict] = None


@router.get(
    "/detail/{poi_id}",
    response_model=POIDetailResponse,
    summary="获取POI详情",
    description="根据POI ID获取详细信息,包括图片"
)
async def get_poi_detail(poi_id: str):
    """
    获取POI详情
    
    Args:
        poi_id: POI ID
        
    Returns:
        POI详情响应
    """
    try:
        amap_service = get_amap_service()
        
        # 调用高德地图POI详情API
        result = amap_service.get_poi_detail(poi_id)
        
        return POIDetailResponse(
            success=True,
            message="获取POI详情成功",
            data=result
        )
        
    except Exception as e:
        print(f"❌ 获取POI详情失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取POI详情失败: {str(e)}"
        )


@router.get(
    "/search",
    summary="搜索POI",
    description="根据关键词搜索POI"
)
async def search_poi(keywords: str, city: str = "北京"):
    """
    搜索POI

    Args:
        keywords: 搜索关键词
        city: 城市名称

    Returns:
        搜索结果
    """
    try:
        amap_service = get_amap_service()
        result = amap_service.search_poi(keywords, city)

        return {
            "success": True,
            "message": "搜索成功",
            "data": result
        }

    except Exception as e:
        print(f"❌ 搜索POI失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"搜索POI失败: {str(e)}"
        )


@router.get(
    "/photo",
    summary="获取景点图片",
    description="根据景点名称从Unsplash获取图片"
)
async def get_attraction_photo(name: str, city: Optional[str] = None):
    """
    获取景点图片

    Args:
        name: 景点名称
        city: 所在城市(用于提升搜索准确率)

    Returns:
        图片URL
    """
    try:
        unsplash_service = get_unsplash_service()

        import pypinyin
        
        # 将景点名称转为无声调的拼音 (例如: 钟楼 -> zhong lou)
        pinyin_list = pypinyin.pinyin(name, style=pypinyin.Style.NORMAL)
        pinyin_name = "".join([p[0] for p in pinyin_list])
        
        # 尝试 1: 景点拼音 + China
        query_attraction = f"{pinyin_name} China"
        photo_url = unsplash_service.get_photo_url(query_attraction)

        if not photo_url:
            # 尝试 2: 如果有城市参数，使用真实的城市拼音做兜底
            if city:
                city_pinyin_list = pypinyin.pinyin(city, style=pypinyin.Style.NORMAL)
                city_pinyin = "".join([p[0] for p in city_pinyin_list])
            else:
                # 非常弱的备用方案(当city为空时)
                city_prefix = name[:2]
                city_pinyin_list = pypinyin.pinyin(city_prefix, style=pypinyin.Style.NORMAL)
                city_pinyin = "".join([p[0] for p in city_pinyin_list])
            
            query_city = f"{city_pinyin} China landmark"
            photo_url = unsplash_service.get_photo_url(query_city, randomize=True)
            
        if not photo_url:
            # 尝试 3: 最泛的兜底，保证一定有图
            photo_url = unsplash_service.get_photo_url("beautiful ancient architecture China", randomize=True)

        return {
            "success": True,
            "message": "获取图片成功",
            "data": {
                "name": name,
                "photo_url": photo_url
            }
        }

    except Exception as e:
        print(f"❌ 获取景点图片失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取景点图片失败: {str(e)}"
        )

