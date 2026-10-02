"""
pairwise-puzzle-system - PuzzleSystem

关卡解谜机关系统：开关、压力板、联动门、重置与存档。
"""

import copy
import hashlib
import json
import time


class PuzzleSystem:
    SAVE_VERSION = 1

    def __init__(self):
        self.state = {}
        self.switches = {}
        self.pressure_plates = {}
        self.doors = {}
        self.linkages = []
        self.solved_puzzles = set()
        self.reset_timers = {}
        self.event_log = []
        self._listeners = {}
        self._initial = {"switches": {}, "plates": {}, "doors": {}, "solved": set()}

    # ---------------------------------------------------------------- events

    def on(self, event, callback):
        """注册事件监听（switch_toggled / plate_triggered / door_changed / puzzle_reset）。"""
        self._listeners.setdefault(event, []).append(callback)

    def _emit(self, event, **payload):
        record = {"event": event, **payload}
        self.event_log.append(record)
        for callback in self._listeners.get(event, []):
            callback(record)

    @staticmethod
    def _now(now):
        return time.monotonic() if now is None else float(now)

    # ------------------------------------------------------------- snapshot

    def _restore_initial(self):
        for sid, saved in self._initial["switches"].items():
            if sid in self.switches:
                self.switches[sid].update(copy.deepcopy(saved))
        for switch in self.switches.values():
            switch["last_trigger"] = None
        for pid, saved in self._initial["plates"].items():
            if pid in self.pressure_plates:
                self.pressure_plates[pid].update(copy.deepcopy(saved))
        for plate in self.pressure_plates.values():
            plate["objects"] = {}
            plate["pressed"] = False
        for did, saved in self._initial["doors"].items():
            if did in self.doors:
                self.doors[did].update(copy.deepcopy(saved))
        self.solved_puzzles = set(self._initial["solved"])
        for link in self.linkages:
            link["pending"] = None

    # ------------------------------------------------------------- switches

    def add_switch(self, switch_id, debounce=0.2, initial=False):
        self.switches[switch_id] = {
            "state": bool(initial),
            "debounce": float(debounce),
            "last_trigger": None,
        }
        self._initial["switches"][switch_id] = copy.deepcopy(
            self.switches[switch_id])

    def trigger_switch(self, switch_id="default", now=None):
        """触发开关：状态取反，带防抖，并驱动联动系统。"""
        now = self._now(now)
        if switch_id not in self.switches:
            self.add_switch(switch_id)
        switch = self.switches[switch_id]
        last = switch["last_trigger"]
        if last is not None and now - last < switch["debounce"]:
            return {
                "switch": switch_id,
                "state": switch["state"],
                "changed": False,
                "debounced": True,
            }
        switch["state"] = not switch["state"]
        switch["last_trigger"] = now
        self._emit("switch_toggled", switch=switch_id, state=switch["state"])
        linkage = self.update_linkage(now=now)
        return {
            "switch": switch_id,
            "state": switch["state"],
            "changed": True,
            "debounced": False,
            "linkage": linkage,
        }

    # -------------------------------------------------------- pressure plate

    def add_pressure_plate(self, plate_id, required_weight=10.0):
        self.pressure_plates[plate_id] = {
            "required_weight": float(required_weight),
            "objects": {},
            "pressed": False,
        }
        self._initial["plates"][plate_id] = copy.deepcopy(
            self.pressure_plates[plate_id])

    def update_pressure_plate(self, plate_id="default", objects=None, now=None):
        """更新压力板：重量阈值检测，支持多物体，踩住期间持续触发。

        objects: 当前压在板上的物体，元素为 (object_id, weight)。
        只有总重量达到 required_weight 才触发；重量不足（轻物体）不触发；
        所有物体离开（或总重低于阈值）才复位。
        """
        now = self._now(now)
        if plate_id not in self.pressure_plates:
            self.add_pressure_plate(plate_id)
        plate = self.pressure_plates[plate_id]
        current = {}
        for obj_id, weight in (objects or []):
            current[obj_id] = float(weight)
        plate["objects"] = current
        total = sum(current.values())
        pressed = total >= plate["required_weight"]
        was_pressed = plate["pressed"]
        plate["pressed"] = pressed
        if pressed:
            self._emit("plate_triggered", plate=plate_id, weight=total,
                       continuous=was_pressed)
            self.update_linkage(now=now)
        elif was_pressed:
            self._emit("plate_released", plate=plate_id, weight=total)
            self.update_linkage(now=now)
        return {
            "plate": plate_id,
            "pressed": pressed,
            "total_weight": total,
            "objects": dict(current),
        }

    # -------------------------------------------------------------- linkage

    def add_linkage(self, output, inputs, gate="AND", delay=0.0):
        """建立联动：inputs（开关/压力板）经逻辑门驱动 output 门，可带延迟。"""
        gate = gate.upper()
        if gate not in ("AND", "OR", "NOT", "XOR"):
            raise ValueError(f"unsupported gate: {gate}")
        self.doors.setdefault(output, {"open": False})
        self._initial["doors"].setdefault(output, {"open": False})
        self.linkages.append({
            "output": output,
            "inputs": list(inputs),
            "gate": gate,
            "delay": float(delay),
            "pending": None,
        })

    def _input_value(self, source):
        if source in self.switches:
            return self.switches[source]["state"]
        if source in self.pressure_plates:
            return self.pressure_plates[source]["pressed"]
        if source in self.doors:
            return self.doors[source]["open"]
        return False

    @staticmethod
    def _evaluate_gate(gate, values):
        if gate == "AND":
            return all(values)
        if gate == "OR":
            return any(values)
        if gate == "NOT":
            return not values[0]
        return sum(bool(value) for value in values) % 2 == 1

    def linkage_feedback(self):
        """反馈：每扇门由哪些开关/压力板、经什么逻辑门控制及当前状态。"""
        return {
            link["output"]: {
                "inputs": list(link["inputs"]),
                "gate": link["gate"],
                "delay": link["delay"],
                "open": self.doors[link["output"]]["open"],
            }
            for link in self.linkages
        }

    def update_linkage(self, now=None):
        """评估所有联动：逻辑门求值，延迟到点后才切换门状态，返回反馈表。"""
        now = self._now(now)
        for link in self.linkages:
            target = self._evaluate_gate(
                link["gate"], [self._input_value(s) for s in link["inputs"]])
            door = self.doors[link["output"]]
            if link["delay"] > 0:
                if target == door["open"]:
                    link["pending"] = None
                    continue
                pending = link["pending"]
                if pending is None or pending["value"] != target:
                    pending = {"due": now + link["delay"], "value": target}
                    link["pending"] = pending
                if now >= pending["due"]:
                    door["open"] = target
                    link["pending"] = None
                    self._emit("door_changed", door=link["output"], open=target)
            elif door["open"] != target:
                door["open"] = target
                self._emit("door_changed", door=link["output"], open=target)
        return self.linkage_feedback()

    # ---------------------------------------------------------------- reset

    def set_auto_reset(self, puzzle_id, interval):
        """设置自动重置周期（秒）。"""
        self.reset_timers[puzzle_id] = {
            "interval": float(interval),
            "last_reset": None,
        }

    def reset_puzzle(self, puzzle_id="default", now=None):
        """重置机关：恢复初始状态，遵守自动重置计时，并发出重置事件。"""
        now = self._now(now)
        timer = self.reset_timers.get(puzzle_id)
        if timer is not None and timer["interval"] is not None:
            last = timer["last_reset"]
            if last is not None and now - last < timer["interval"]:
                return {
                    "puzzle": puzzle_id,
                    "reset": False,
                    "retry_in": timer["interval"] - (now - last),
                }
        else:
            timer = self.reset_timers.setdefault(
                puzzle_id, {"interval": None, "last_reset": None})
        self._restore_initial()
        timer["last_reset"] = now
        self._emit("puzzle_reset", puzzle=puzzle_id, time=now)
        return {"puzzle": puzzle_id, "reset": True, "time": now}

    # ----------------------------------------------------------------- save

    def mark_solved(self, puzzle_id):
        self.solved_puzzles.add(puzzle_id)

    def save_puzzle_state(self):
        """存档：保存开关/压力板/门状态与解谜进度，附带校验和。"""
        payload = {
            "version": self.SAVE_VERSION,
            "switches": {sid: sw["state"] for sid, sw in self.switches.items()},
            "plates": {
                pid: {"pressed": pl["pressed"], "objects": dict(pl["objects"])}
                for pid, pl in self.pressure_plates.items()
            },
            "doors": {did: door["open"] for did, door in self.doors.items()},
            "solved": sorted(self.solved_puzzles),
        }
        blob = json.dumps(payload, sort_keys=True)
        checksum = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return {"payload": payload, "checksum": checksum}

    def load_puzzle_state(self, save):
        """读档：先校验完整性，损坏的存档抛出 ValueError 而不是崩溃。"""
        if not isinstance(save, dict) or "payload" not in save \
                or "checksum" not in save:
            raise ValueError("corrupted save: missing payload or checksum")
        payload = save["payload"]
        blob = json.dumps(payload, sort_keys=True)
        if hashlib.sha256(blob.encode("utf-8")).hexdigest() != save["checksum"]:
            raise ValueError("corrupted save: checksum mismatch")
        if payload.get("version") != self.SAVE_VERSION:
            raise ValueError("unsupported save version")
        for sid, state in payload["switches"].items():
            if sid in self.switches:
                self.switches[sid]["state"] = bool(state)
        for pid, saved in payload["plates"].items():
            if pid in self.pressure_plates:
                self.pressure_plates[pid]["pressed"] = bool(saved["pressed"])
                self.pressure_plates[pid]["objects"] = dict(saved["objects"])
        for did, open_ in payload["doors"].items():
            if did in self.doors:
                self.doors[did]["open"] = bool(open_)
        self.solved_puzzles = set(payload["solved"])
        return True
