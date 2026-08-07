"""
L5 瞬时记忆管理
滑动窗口保存最近 N 步的感知与决策，快速读写供辩论 Agent 使用。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class InstantMemoryEntry:
    """单步瞬时记忆"""
    timestamp: datetime
    cycle_id: int
    price: float
    action: str                    # long | short | hold
    confidence: float
    pnl: float = 0.0
    regime: str = "unknown"
    summary: str = ""              # 决策简述


class InstantMemory:
    """固定窗口滑动记忆，最新 N 步"""

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self._buffer: deque[InstantMemoryEntry] = deque(maxlen=window_size)

    def push(self, entry: InstantMemoryEntry):
        self._buffer.append(entry)

    def get_all(self) -> list[InstantMemoryEntry]:
        return list(self._buffer)

    def get_recent(self, n: int = 5) -> list[InstantMemoryEntry]:
        n = min(n, len(self._buffer))
        return list(self._buffer)[-n:]

    def last(self) -> Optional[InstantMemoryEntry]:
        return self._buffer[-1] if self._buffer else None

    def win_rate(self) -> float:
        """最近窗口胜率"""
        trades = [e for e in self._buffer if e.action in ("long", "short")]
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.pnl > 0)
        return wins / len(trades)

    def avg_confidence(self) -> float:
        if not self._buffer:
            return 0.0
        return sum(e.confidence for e in self._buffer) / len(self._buffer)

    def regime_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {}
        for e in self._buffer:
            dist[e.regime] = dist.get(e.regime, 0) + 1
        return dist

    def __len__(self):
        return len(self._buffer)
