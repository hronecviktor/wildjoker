"""CPU difficulty levels.

A level combines three separate dials, each its own dataclass, so custom
mixes are a one-liner (``Level("mixed", EXPERT.speed, EASY.moves,
HARD.smarts)``):

- ``Speed``: how quickly a CPU notices a change, works out a move and draws.
- ``Moves``: what kinds of moves it can find, and how often it overlooks one.
- ``Smarts``: which of the moves it found it plays, and when.

All times are in seconds at normal speed; the server can scale them with
``Settings.cpu_speed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Speed:
    # Delay after a change before looking at the table again (uniform range).
    reaction: tuple[float, float]
    # Time to work out a move: base + per card moved + per pile staged.
    think_base: float
    think_per_card: float
    think_per_pile: float
    # Minimum time between draws while there is nothing to play (uniform range).
    draw_interval: tuple[float, float]
    # Pause between staging piles and committing, so the others see it happen.
    stage_pause: float


@dataclass(frozen=True)
class Moves:
    # "add": add hand cards to a pile, new piles from the hand.
    # "take": also take cards from a pile and swap jokers (one pile at a time).
    # "rearrange": also split, merge and rearrange up to ``max_piles`` piles.
    # "full": the solver across any number of piles.
    kind: Literal["add", "take", "rearrange", "full"]
    max_piles: int
    # Chance of overlooking each move it could make, per look at the table.
    miss: float
    # Solver calls per look (for the pile-by-pile search), time limit per
    # call, and in total per look.
    max_solves: int = 60
    time_limit: float = 0.5
    search_time: float = 1.5


@dataclass(frozen=True)
class Smarts:
    # "any": plays whichever move it found; "best": the one shedding most.
    pick: Literal["any", "best"]
    # Solver weight of a joker (real cards weigh 1). Below zero, jokers stay
    # in the hand unless they let real cards out.
    joker_weight: float
    # Opens with its longest run rather than the first one it sees.
    open_longest: bool
    # Plays moves on the table (where someone else might take the spot first)
    # before moves that only put new piles down from the hand, which nobody
    # else can use yet.
    contested_first: bool = False
    # Holds back hand-only moves this long while it is not close to going out
    # or racing, even with nothing else to do. 0 turns it off. In simulations
    # holding back made Expert lose more often, so no level uses it.
    patience: float = 0.0
    # Races (plays everything, faster) once an opponent has this few cards.
    race_below: int = 0


@dataclass(frozen=True)
class Level:
    name: str
    speed: Speed
    moves: Moves
    smarts: Smarts


EASY = Level(
    "easy",
    Speed((6.0, 10.0), 2.0, 0.5, 1.0, (8.0, 12.0), 1.5),
    Moves("add", max_piles=1, miss=0.3),
    Smarts("any", joker_weight=1.0, open_longest=False),
)
MEDIUM = Level(
    "medium",
    Speed((3.0, 6.0), 1.5, 0.3, 0.6, (5.0, 8.0), 1.0),
    Moves("take", max_piles=1, miss=0.15, max_solves=25),
    Smarts("best", joker_weight=0.9, open_longest=True),
)
HARD = Level(
    "hard",
    Speed((1.5, 3.0), 1.0, 0.2, 0.4, (3.0, 5.0), 0.8),
    Moves("rearrange", max_piles=3, miss=0.0),
    Smarts("best", joker_weight=-0.25, open_longest=True),
)
EXPERT = Level(
    "expert",
    Speed((0.5, 1.5), 0.5, 0.1, 0.2, (2.0, 3.0), 0.5),
    Moves("full", max_piles=99, miss=0.0, max_solves=80, time_limit=1.0, search_time=2.5),
    Smarts("best", joker_weight=-0.25, open_longest=True, contested_first=True, race_below=3),
)

LEVELS: dict[str, Level] = {level.name: level for level in (EASY, MEDIUM, HARD, EXPERT)}
