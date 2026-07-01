from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DailyEmailContent:
    subject: str
    plain_text: str
    html: str