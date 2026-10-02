"""
pairwise-puzzle-system - PuzzleSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class PuzzleSystem:
    def __init__(self):
        self.state = {}

    def trigger_switch(self, *args, **kwargs):
        """BUG: 开关触发不做状态切换，按了还是开"""
        return None

    def update_pressure_plate(self, *args, **kwargs):
        """BUG: 压力板不做重量检测，轻物体也能触发"""
        return None

    def update_linkage(self, *args, **kwargs):
        """BUG: 联动不做逻辑，不支持与或非门"""
        return None

    def reset_puzzle(self, *args, **kwargs):
        """BUG: 机关重置不做状态恢复，重置后还是解开的"""
        return None

    def save_puzzle_state(self, *args, **kwargs):
        """BUG: 机关存档不存状态，读档后机关全复位"""
        return None

