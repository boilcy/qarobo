"""
Calculator functions for function calling demos.

这个模块提供基本的计算器功能，包括加减乘除操作。
"""

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams


# 计算器函数实现
async def calculate_add(params: FunctionCallParams):
    """执行加法运算"""
    logger.info(f"计算加法: {params.arguments}")

    try:
        a = float(params.arguments.get("a", 0))
        b = float(params.arguments.get("b", 0))
        result = a + b

        await params.result_callback(
            {
                "operation": "add",
                "a": a,
                "b": b,
                "result": result,
                "expression": f"{a} + {b} = {result}",
            }
        )
    except Exception as e:
        logger.error(f"加法运算错误: {e}")
        await params.result_callback({"error": str(e)})


async def calculate_subtract(params: FunctionCallParams):
    """执行减法运算"""
    logger.info(f"计算减法: {params.arguments}")

    try:
        a = float(params.arguments.get("a", 0))
        b = float(params.arguments.get("b", 0))
        result = a - b

        await params.result_callback(
            {
                "operation": "subtract",
                "a": a,
                "b": b,
                "result": result,
                "expression": f"{a} - {b} = {result}",
            }
        )
    except Exception as e:
        logger.error(f"减法运算错误: {e}")
        await params.result_callback({"error": str(e)})


async def calculate_multiply(params: FunctionCallParams):
    """执行乘法运算"""
    logger.info(f"计算乘法: {params.arguments}")

    try:
        a = float(params.arguments.get("a", 0))
        b = float(params.arguments.get("b", 0))
        result = a * b

        await params.result_callback(
            {
                "operation": "multiply",
                "a": a,
                "b": b,
                "result": result,
                "expression": f"{a} × {b} = {result}",
            }
        )
    except Exception as e:
        logger.error(f"乘法运算错误: {e}")
        await params.result_callback({"error": str(e)})


async def calculate_divide(params: FunctionCallParams):
    """执行除法运算"""
    logger.info(f"计算除法: {params.arguments}")

    try:
        a = float(params.arguments.get("a", 0))
        b = float(params.arguments.get("b", 0))

        if b == 0:
            await params.result_callback({"error": "除数不能为零"})
            return

        result = a / b

        await params.result_callback(
            {
                "operation": "divide",
                "a": a,
                "b": b,
                "result": result,
                "expression": f"{a} ÷ {b} = {result}",
            }
        )
    except Exception as e:
        logger.error(f"除法运算错误: {e}")
        await params.result_callback({"error": str(e)})


# 函数模式定义
add_function_schema = FunctionSchema(
    name="calculate_add",
    description="执行两个数字的加法运算",
    properties={
        "a": {
            "type": "number",
            "description": "第一个加数",
        },
        "b": {
            "type": "number",
            "description": "第二个加数",
        },
    },
    required=["a", "b"],
)

subtract_function_schema = FunctionSchema(
    name="calculate_subtract",
    description="执行两个数字的减法运算",
    properties={
        "a": {
            "type": "number",
            "description": "被减数",
        },
        "b": {
            "type": "number",
            "description": "减数",
        },
    },
    required=["a", "b"],
)

multiply_function_schema = FunctionSchema(
    name="calculate_multiply",
    description="执行两个数字的乘法运算",
    properties={
        "a": {
            "type": "number",
            "description": "第一个乘数",
        },
        "b": {
            "type": "number",
            "description": "第二个乘数",
        },
    },
    required=["a", "b"],
)

divide_function_schema = FunctionSchema(
    name="calculate_divide",
    description="执行两个数字的除法运算",
    properties={
        "a": {
            "type": "number",
            "description": "被除数",
        },
        "b": {
            "type": "number",
            "description": "除数（不能为零）",
        },
    },
    required=["a", "b"],
)


def get_calculator_tools() -> ToolsSchema:
    """获取所有计算器工具的 ToolsSchema"""
    return ToolsSchema(
        standard_tools=[
            add_function_schema,
            subtract_function_schema,
            multiply_function_schema,
            divide_function_schema,
        ]
    )


def register_calculator_functions(llm):
    """
    将所有计算器函数注册到 LLM 服务

    Args:
        llm: LLM 服务实例
    """
    llm.register_function("calculate_add", calculate_add)
    llm.register_function("calculate_subtract", calculate_subtract)
    llm.register_function("calculate_multiply", calculate_multiply)
    llm.register_function("calculate_divide", calculate_divide)
    logger.info("已注册所有计算器函数")
