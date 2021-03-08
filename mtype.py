from enum import IntEnum
from collections import namedtuple

BranchT = namedtuple("BranchT", "index pc cond hash vars file")
ScoreT = namedtuple("ScoreT", "new ummio nmmio")

class Cond(IntEnum):
    FALSE = 0
    TRUE = 1
    SWITCH = 2
    BOTH = 3
    RANDOM = 4

    