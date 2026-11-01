"""Dataclasses shared across the app. Extended in later milestones."""
from dataclasses import dataclass


@dataclass
class Settings:
    name: str = ""
    monthly_budget: float | None = None
    cycle_start_day: int = 1
