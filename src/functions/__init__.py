"""
Functions module for function calling demos.
"""

from .calculator import (
    calculate_add,
    calculate_subtract,
    calculate_multiply,
    calculate_divide,
    get_calculator_tools,
)

from .weather import (
    get_current_weather,
    get_weather_forecast,
    get_weather_tools,
)

__all__ = [
    # Calculator functions
    "calculate_add",
    "calculate_subtract",
    "calculate_multiply",
    "calculate_divide",
    "get_calculator_tools",
    # Weather functions
    "get_current_weather",
    "get_weather_forecast",
    "get_weather_tools",
]
