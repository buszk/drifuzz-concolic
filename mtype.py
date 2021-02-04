from enum import IntEnum
from collections import namedtuple

BranchT = namedtuple("BranchT", "index pc cond hash vars file")
ScoreT = namedtuple("ScoreT", "ummio nmmio")

class Cond(IntEnum):
    FALSE = 0 #false
    TRUE = 1 #true
    BOTH = 2 #both

    