"""Shared business-rule helpers."""

from typing import Iterable


ABNORMAL_STATES = {
    "异常",
    "较差",
    "差",
    "偏差较大",
    "偏离显著",
    "偏高",
    "偏低",
    "严重偏高",
    "严重偏低",
}

NON_ABNORMAL_ACCEPTABLE_STATES = {
    "待机备用",
}


def is_abnormal_state(state_desc: str, abnormal_states: Iterable[str] = ABNORMAL_STATES) -> bool:
    return (state_desc or "") in abnormal_states
