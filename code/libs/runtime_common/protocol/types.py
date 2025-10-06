from enum import Enum, auto

class ConnectionRole(Enum):
    CLIENT = auto()
    CONTROLLER = auto()
    OBSERVER = auto()

class RunState(Enum):
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    PREEMPTED = auto()
    COMPLETED = auto()
    ERROR = auto()
