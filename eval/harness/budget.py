"""Spend guard for benchmark runs (spec 000 AC10)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ports.llm import Usage


class BudgetExceededError(RuntimeError):
    pass


@dataclass
class BudgetGuard:
    max_usd: float
    spent_usd: float = 0.0
    calls: list[Usage] = field(default_factory=list)

    def check(self) -> None:
        """Call before each request; refuses once the cap is reached."""
        if self.spent_usd >= self.max_usd:
            raise BudgetExceededError(
                f"Budget exhausted: spent ${self.spent_usd:.4f} of ${self.max_usd:.2f}"
            )

    def record(self, usage: Usage) -> None:
        self.calls.append(usage)
        self.spent_usd += usage.cost_usd

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.max_usd - self.spent_usd)
