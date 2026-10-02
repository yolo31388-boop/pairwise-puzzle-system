"""
pairwise-puzzle-system - PuzzleSystem

开关 / 压力板 / 联动 / 重置 / 存档 的完整机关系统实现。
"""

import copy
import hashlib
import json
import time


class PuzzleSystem:
    DEBOUNCE_INTERVAL = 0.2  # 开关防抖间隔（秒）

    def __init__(self):
        self.state = {}
        self.switches = {}
        self.pressure_plates = {}
        self.doors = {}
        self.linkages = []
        self.solved = False
        self.progress = {"solved": []}
        self.events = []
        self._listeners = {}
        self._initial_snapshot = None
        self._reset_deadline = None

    # ---------------------------------------------------------------- events
    def on(self, event, callback):
        """注册事件监听器。"""
        self._listeners.setdefault(event, []).append(callback)
        return callback

    def _emit(self, event, data):
        record = {"event": event, "data": data, "time": time.monotonic()}
        self.events.append(record)
        for callback in self._listeners.get(event, []):
            callback(data)
        return record

    # ------------------------------------------------------------- snapshot
    def _snapshot(self):
        return {
            "switches": {sid: sw["state"] for sid, sw in self.switches.items()},
            "doors": {did: door["open"] for did, door in self.doors.items()},
            "pressure_plates": {
                pid: {"active": pl["active"], "objects": dict(pl["objects"])}
                for pid, pl in self.pressure_plates.items()
            },
            "solved": self.solved,
        }

    def _ensure_initial_snapshot(self):
        if self._initial_snapshot is None:
            self._initial_snapshot = copy.deepcopy(self._snapshot())

    # ------------------------------------------------------------- switches
    def add_switch(self, switch_id, state=False):
        self.switches[switch_id] = {"state": bool(state), "last_trigger": None}
        return self.switches[switch_id]

    def trigger_switch(self, switch_id=None, now=None, **kwargs):
        """触发开关：状态切换 + 防抖 + 联动。"""
        now = time.monotonic() if now is None else now
        self._ensure_initial_snapshot()
        if switch_id is None:
            if not self.switches:
                self.add_switch("switch_0")
            switch_id = next(iter(self.switches))
        switch = self.switches.get(switch_id)
        if switch is None:
            switch = self.add_switch(switch_id)

        last = switch["last_trigger"]
        if last is not None and now - last < self.DEBOUNCE_INTERVAL:
            # 防抖：间隔过短的重复触发直接忽略，状态不变
            return {"switch": switch_id, "state": switch["state"],
                    "debounced": True, "changed": False}

        switch["state"] = not switch["state"]
        switch["last_trigger"] = now
        self._emit("switch_toggled",
                   {"switch": switch_id, "state": switch["state"]})
        linkage = self.update_linkage(now=now)
        return {"switch": switch_id, "state": switch["state"],
                "debounced": False, "changed": True, "linkage": linkage}

    # -------------------------------------------------------- pressure plate
    def add_pressure_plate(self, plate_id, threshold=10.0, min_object_weight=1.0):
        self.pressure_plates[plate_id] = {
            "threshold": float(threshold),
            "min_object_weight": float(min_object_weight),
            "objects": {},
            "active": False,
            "trigger_count": 0,
        }
        return self.pressure_plates[plate_id]

    def update_pressure_plate(self, plate_id=None, objects=None, now=None, **kwargs):
        """更新压力板：重量检测 + 多物体追踪 + 持续触发。

        objects: 当前站在板上的物体，dict {obj_id: weight} 或
                 [(obj_id, weight), ...]。重量低于 min_object_weight 的
                 轻物体被忽略；总重量达到 threshold 才触发；所有物体
                 离开（或总重不足）才复位；激活期间每次更新都算一次
                 持续触发并发出事件。
        """
        self._ensure_initial_snapshot()
        if plate_id is None:
            if not self.pressure_plates:
                self.add_pressure_plate("plate_0")
            plate_id = next(iter(self.pressure_plates))
        plate = self.pressure_plates.get(plate_id)
        if plate is None:
            plate = self.add_pressure_plate(plate_id)

        current = {}
        if objects:
            items = objects.items() if isinstance(objects, dict) else objects
            for obj_id, weight in items:
                if weight >= plate["min_object_weight"]:
                    current[obj_id] = float(weight)
        plate["objects"] = current

        total_weight = sum(current.values())
        plate["active"] = bool(current) and total_weight >= plate["threshold"]

        if plate["active"]:
            # 持续触发：只要压着，每次更新都计一次触发
            plate["trigger_count"] += 1
            self._emit("plate_triggered", {
                "plate": plate_id,
                "total_weight": total_weight,
                "objects": list(current),
                "count": plate["trigger_count"],
            })
        elif not current:
            # 所有物体离开才复位
            plate["trigger_count"] = 0

        return {"plate": plate_id, "active": plate["active"],
                "total_weight": total_weight, "objects": list(current),
                "trigger_count": plate["trigger_count"]}

    # -------------------------------------------------------------- linkage
    def add_door(self, door_id, open=False):
        self.doors[door_id] = {"open": bool(open)}
        return self.doors[door_id]

    def add_linkage(self, inputs, output, gate="AND", delay=0.0, linkage_id=None):
        linkage_id = linkage_id or f"linkage_{len(self.linkages)}"
        if output not in self.doors:
            self.add_door(output)
        linkage = {
            "id": linkage_id,
            "inputs": list(inputs),
            "output": output,
            "gate": str(gate).upper(),
            "delay": float(delay),
            "pending": None,
        }
        self.linkages.append(linkage)
        return linkage

    def _evaluate_gate(self, linkage):
        values = [self.switches.get(sid, {}).get("state", False)
                  for sid in linkage["inputs"]]
        gate = linkage["gate"]
        if gate == "AND":
            return bool(values) and all(values)
        if gate == "OR":
            return any(values)
        if gate == "NOT":
            return not any(values)
        raise ValueError(f"unsupported gate: {gate}")

    def _apply_door(self, linkage, value, now):
        door = self.doors[linkage["output"]]
        if door["open"] == value:
            return False
        door["open"] = value
        # 反馈：报告哪个开关组合控制了哪扇门
        self._emit("linkage_feedback", {
            "linkage": linkage["id"],
            "inputs": list(linkage["inputs"]),
            "output": linkage["output"],
            "open": value,
        })
        return True

    def update_linkage(self, linkage_id=None, now=None, **kwargs):
        """求值联动：与/或/非逻辑门 + 延迟 + 反馈。"""
        now = time.monotonic() if now is None else now
        results = {}
        for linkage in self.linkages:
            if linkage_id is not None and linkage["id"] != linkage_id:
                continue

            # 到期的延迟变化先生效
            pending = linkage["pending"]
            fired_pending = False
            if pending is not None and now >= pending["due"]:
                linkage["pending"] = None
                fired_pending = self._apply_door(linkage, pending["value"], now)

            target = self._evaluate_gate(linkage)
            door = self.doors[linkage["output"]]
            scheduled = False
            if linkage["pending"] is None and target != door["open"]:
                if linkage["delay"] > 0:
                    # 延迟：开关变化后过一段时间门才变化
                    linkage["pending"] = {"value": target,
                                          "due": now + linkage["delay"]}
                    scheduled = True
                else:
                    self._apply_door(linkage, target, now)

            results[linkage["id"]] = {
                "inputs": list(linkage["inputs"]),
                "output": linkage["output"],
                "gate": linkage["gate"],
                "open": door["open"],
                "pending": linkage["pending"] is not None or scheduled,
                "fired": fired_pending,
            }
        return {"linkages": results,
                "feedback": {ln["id"]: {"inputs": list(ln["inputs"]),
                                        "output": ln["output"]}
                             for ln in self.linkages}}

    # ---------------------------------------------------------------- reset
    def schedule_auto_reset(self, delay, now=None):
        """按时间自动重置：delay 秒后 reset_puzzle 才生效。"""
        now = time.monotonic() if now is None else now
        self._reset_deadline = now + float(delay)
        return self._reset_deadline

    def reset_puzzle(self, now=None, **kwargs):
        """重置机关：状态恢复 + 计时 + 事件通知。"""
        now = time.monotonic() if now is None else now

        # 计时：自动重置未到时间则不重置
        if self._reset_deadline is not None and now < self._reset_deadline:
            return {"reset": False,
                    "remaining": self._reset_deadline - now}
        self._reset_deadline = None

        # 状态恢复：回到初始快照
        if self._initial_snapshot is not None:
            snap = copy.deepcopy(self._initial_snapshot)
            for sid, state in snap["switches"].items():
                if sid in self.switches:
                    self.switches[sid]["state"] = state
                    self.switches[sid]["last_trigger"] = None
            for did, open_ in snap["doors"].items():
                if did in self.doors:
                    self.doors[did]["open"] = open_
            for pid, plate in snap["pressure_plates"].items():
                if pid in self.pressure_plates:
                    self.pressure_plates[pid]["objects"] = dict(plate["objects"])
                    self.pressure_plates[pid]["active"] = plate["active"]
                    self.pressure_plates[pid]["trigger_count"] = 0
            self.solved = snap["solved"]
        for linkage in self.linkages:
            linkage["pending"] = None

        # 事件：通知所有监听者机关已重置
        self._emit("puzzle_reset", {"state": self._snapshot()})
        return {"reset": True, "state": self._snapshot()}

    # ----------------------------------------------------------------- save
    def save_puzzle_state(self, path=None, **kwargs):
        """存档：保存机关状态 + 解谜进度，并附校验和。"""
        payload = {
            "state": self._snapshot(),
            "progress": {"solved": list(self.progress.get("solved", []))},
        }
        blob = json.dumps(payload, sort_keys=True)
        save = {"payload": payload,
                "checksum": hashlib.sha256(blob.encode("utf-8")).hexdigest()}
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(save, fh)
        return save

    def load_puzzle_state(self, source):
        """读档：先校验 checksum，损坏的存档抛 ValueError 而不是崩溃。"""
        if isinstance(source, (str, bytes)):
            with open(source, "r", encoding="utf-8") as fh:
                save = json.load(fh)
        else:
            save = source
        if not isinstance(save, dict) or "payload" not in save or "checksum" not in save:
            raise ValueError("corrupted save: missing payload or checksum")
        blob = json.dumps(save["payload"], sort_keys=True)
        expected = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        if expected != save["checksum"]:
            raise ValueError("corrupted save: checksum mismatch")

        state = save["payload"]["state"]
        for sid, sw_state in state.get("switches", {}).items():
            self.switches.setdefault(sid, {"last_trigger": None})["state"] = sw_state
        for did, open_ in state.get("doors", {}).items():
            self.doors.setdefault(did, {})["open"] = open_
        for pid, plate in state.get("pressure_plates", {}).items():
            target = self.pressure_plates.setdefault(pid, {
                "threshold": 10.0, "min_object_weight": 1.0,
                "objects": {}, "active": False, "trigger_count": 0})
            target["objects"] = dict(plate.get("objects", {}))
            target["active"] = plate.get("active", False)
        self.solved = state.get("solved", False)
        self.progress["solved"] = list(
            save["payload"].get("progress", {}).get("solved", []))
        return self._snapshot()
