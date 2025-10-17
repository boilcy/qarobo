"""
Weather functions for function calling demos.

这个模块提供天气查询功能（演示用）。
"""

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams


# 天气函数实现（演示版本，返回模拟数据）
async def get_current_weather(params: FunctionCallParams):
    """获取指定位置的当前天气"""
    logger.info(f"查询天气: {params.arguments}")

    try:
        location = params.arguments.get("location", "未知位置")
        format_unit = params.arguments.get("format", "celsius")

        # 模拟天气数据
        weather_data = {
            "北京": {"temp_c": 15, "temp_f": 59, "condition": "晴朗"},
            "上海": {"temp_c": 20, "temp_f": 68, "condition": "多云"},
            "深圳": {"temp_c": 25, "temp_f": 77, "condition": "小雨"},
            "广州": {"temp_c": 26, "temp_f": 79, "condition": "晴朗"},
        }

        # 默认数据
        default_data = {"temp_c": 22, "temp_f": 72, "condition": "晴朗"}

        # 查找匹配的城市
        city_data = None
        for city, data in weather_data.items():
            if city in location:
                city_data = data
                break

        if not city_data:
            city_data = default_data

        # 根据温度单位返回相应数据
        if format_unit.lower() == "fahrenheit":
            temperature = city_data["temp_f"]
            unit = "华氏度"
        else:
            temperature = city_data["temp_c"]
            unit = "摄氏度"

        result = {
            "location": location,
            "temperature": temperature,
            "unit": unit,
            "conditions": city_data["condition"],
            "description": f"{location}当前天气{city_data['condition']}，温度{temperature}{unit}",
        }

        logger.info(f"天气查询结果: {result}")
        await params.result_callback(result)

    except Exception as e:
        logger.error(f"天气查询错误: {e}")
        await params.result_callback({"error": str(e)})


async def get_weather_forecast(params: FunctionCallParams):
    """获取指定位置的天气预报（未来几天）"""
    logger.info(f"查询天气预报: {params.arguments}")

    try:
        location = params.arguments.get("location", "未知位置")
        days = params.arguments.get("days", 3)

        # 模拟天气预报数据
        forecast = []
        conditions = ["晴朗", "多云", "小雨", "阴天"]

        for i in range(min(days, 7)):  # 最多7天
            day_forecast = {
                "day": f"第{i + 1}天",
                "high": 25 + i,
                "low": 15 + i,
                "condition": conditions[i % len(conditions)],
            }
            forecast.append(day_forecast)

        result = {
            "location": location,
            "days": days,
            "forecast": forecast,
            "description": f"{location}未来{days}天天气预报",
        }

        logger.info(f"天气预报查询结果: {result}")
        await params.result_callback(result)

    except Exception as e:
        logger.error(f"天气预报查询错误: {e}")
        await params.result_callback({"error": str(e)})


# 函数模式定义
current_weather_schema = FunctionSchema(
    name="get_current_weather",
    description="获取指定位置的当前天气信息",
    properties={
        "location": {
            "type": "string",
            "description": "城市和地区，例如：北京、上海",
        },
        "format": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"],
            "description": "温度单位，从用户位置自动推断。中国使用摄氏度(celsius)。",
        },
    },
    required=["location", "format"],
)

weather_forecast_schema = FunctionSchema(
    name="get_weather_forecast",
    description="获取指定位置未来几天的天气预报",
    properties={
        "location": {
            "type": "string",
            "description": "城市和地区，例如：北京、上海",
        },
        "days": {
            "type": "integer",
            "description": "预报天数，默认3天，最多7天",
        },
    },
    required=["location"],
)


def get_weather_tools() -> ToolsSchema:
    """获取所有天气工具的 ToolsSchema"""
    return ToolsSchema(
        standard_tools=[
            current_weather_schema,
            weather_forecast_schema,
        ]
    )


def register_weather_functions(llm):
    """
    将所有天气函数注册到 LLM 服务

    Args:
        llm: LLM 服务实例
    """
    llm.register_function("get_current_weather", get_current_weather)
    llm.register_function("get_weather_forecast", get_weather_forecast)
    logger.info("已注册所有天气函数")
