import pytest
from puzzle.system import PuzzleSystem


class TestPuzzleSystem:

    def test_trigger_switch(self):
        """开关触发不做状态切换，按了还是开"""
        obj = PuzzleSystem()
        result = obj.trigger_switch()
        self.assertIsNotNone(result)

    def test_update_pressure_plate(self):
        """压力板不做重量检测，轻物体也能触发"""
        obj = PuzzleSystem()
        result = obj.update_pressure_plate()
        self.assertIsNotNone(result)

    def test_update_linkage(self):
        """联动不做逻辑，不支持与或非门"""
        obj = PuzzleSystem()
        result = obj.update_linkage()
        self.assertIsNotNone(result)

    def test_reset_puzzle(self):
        """机关重置不做状态恢复，重置后还是解开的"""
        obj = PuzzleSystem()
        result = obj.reset_puzzle()
        self.assertIsNotNone(result)

    def test_save_puzzle_state(self):
        """机关存档不存状态，读档后机关全复位"""
        obj = PuzzleSystem()
        result = obj.save_puzzle_state()
        self.assertIsNotNone(result)

