"""Conversational wrapper over the planner's engines.

This is deliberately NOT a fake LLM. It's a deterministic intent parser
that routes natural language to the right engine (compare / budget /
whatif / insights / intercity) and narrates the results in plain English.
Everything it says is backed by a real computation you can inspect.

Supported intents:
  - "cheapest way to get there"        -> compare (cheapest profile)
  - "fastest option"                   -> compare (fastest profile)
  - "what if it rains tomorrow"        -> weather + forecast
  - "what if I miss the bus"           -> missed_bus scenario
  - "when should I leave"              -> departure window insight
  - "can I afford uber every day"      -> budget with chosen mode
  - "is the monthly pass worth it"     -> breakeven math
  - "how do I get to ottawa"           -> intercity options
  - "how risky is this route"          -> fragility insight
  - "plan my week"                     -> weekly optimizer
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ChatIntent:
    name: str
    confidence: float
    params: dict = field(default_factory=dict)


INTENT_PATTERNS = [
    ("cheapest", [r"\bcheap", r"\blowest cost", r"\bsave money",
                  r"\bmost affordable", r"\bbudget friendly"]),
    ("fastest", [r"\bfast", r"\bquick", r"\bhurry", r"\bsoonest",
                 r"\bshortest time"]),
    ("weather", [r"\brain", r"\bsnow", r"\bstorm", r"\bweather",
                 r"\bcold", r"\bhot outside"]),
    ("missed_bus", [r"\bmiss", r"\blate for", r"\brunning behind",
                    r"\bjust left", r"\bnext bus"]),
    ("departure_window", [r"\bwhen should i leave", r"\bbest time to leave",
                          r"\bleave earlier", r"\bleave later",
                          r"\bwhat time"]),
    ("budget_check", [r"\bafford", r"\bbudget", r"\bspend",
                      r"\btoo expensive", r"\bcost.*month"]),
    ("monthly_pass", [r"\bmonthly pass", r"\bpass worth", r"\bseason pass",
                      r"\bunlimited"]),
    ("intercity", [r"\bottawa", r"\bmontreal", r"\bkingston",
                   r"\btoronto", r"\bunion station", r"\bgo train",
                   r"\bvia rail", r"\bmegabus", r"\bflixbus",
                   r"\bpoparide", r"\bcarpool", r"\blong distance"]),
    ("fragility", [r"\brisky", r"\breliable", r"\bmiss.*transfer",
                   r"\bconnection", r"\btight"]),
    ("weekly", [r"\bweek", r"\bweekly", r"\bevery day", r"\broutine",
                r"\bcommute pattern"]),
    ("surplus", [r"\bleftover", r"\bsurplus", r"\bextra money",
                 r"\bwhat.*do with", r"\bspare.*budget"]),
]


def parse_intent(message: str) -> ChatIntent:
    """Keyword-based routing with simple scoring. Transparent by design."""
    text = message.lower()
    scores: dict[str, int] = {}
    for name, patterns in INTENT_PATTERNS:
        hits = sum(1 for p in patterns if re.search(p, text))
        if hits:
            scores[name] = hits

    if not scores:
        return ChatIntent("help", 0.0)

    best = max(scores.items(), key=lambda kv: kv[1])
    confidence = min(1.0, best[1] / 3)  # 3+ hits = full confidence

    params: dict = {}
    if best[0] == "budget_check":
        m = re.search(r"\$\s?(\d+)", text)
        if m:
            params["budget"] = float(m.group(1))
        m = re.search(r"(\d+)\s*(?:trips|times)", text)
        if m:
            params["trips_per_week"] = int(m.group(1))

    return ChatIntent(best[0], confidence, params)


HELP_TEXT = (
    "I can help you compare modes (\"cheapest way there\"), plan around "
    "weather (\"what if it rains\"), check your budget (\"can I afford "
    "uber daily on $150?\"), find long-distance options (\"how do I get "
    "to Ottawa\"), assess connection risk (\"is this route reliable\"), "
    "or plan your commuting week (\"plan my week\"). What do you need?"
)
