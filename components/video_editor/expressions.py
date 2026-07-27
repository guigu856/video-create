"""关键帧表达式引擎：把关键帧序列编译为 FFmpeg 逐帧表达式。"""

from __future__ import annotations

from .models import Keyframe


def _num(value: int | float) -> str:
    return format(value, ".12g")


def resolve_property(
    keyframes: list[Keyframe],
    prop: str,
    base: float,
    t_offset: float,
) -> str:
    """将属性的关键帧序列编译为 FFmpeg 表达式字符串。

    关键帧为空或仅一个点时返回基线常量；多个点时返回分段线性
    if/lt 嵌套表达式。返回值中的逗号已转义为 ``\\,``，可直接拼入
    filtergraph。``t_offset`` 为 clip 的 timeline_start，用于把关键帧
    本地时间换算为全局时间。
    """
    points = [
        (keyframe.time + t_offset, getattr(keyframe, prop))
        for keyframe in keyframes
        if getattr(keyframe, prop) is not None
    ]
    if len(points) < 2:
        return _num(base)

    expr = _num(points[-1][1])
    for index in range(len(points) - 2, -1, -1):
        t0, value0 = points[index]
        t1, value1 = points[index + 1]
        if abs(value1 - value0) < 1e-9:
            segment = _num(value0)
        else:
            segment = (
                f"{_num(value0)}+({_num(value1 - value0)})"
                f"*(t-{_num(t0)})/({_num(t1 - t0)})"
            )
        expr = f"if(lt(t\\,{_num(t1)})\\,{segment}\\,{expr})"
    return f"if(lt(t\\,{_num(points[0][0])})\\,{_num(base)}\\,{expr})"


def is_dynamic(expression: str) -> bool:
    """表达式是否依赖时间变量 t。"""
    return "lt(t" in expression
