from models.enums import SymbolState


class SymbolStateMachine:
    def __init__(self):
        self._state = SymbolState.IDLE

    @property
    def state(self) -> SymbolState:
        return self._state

    @state.setter
    def state(self, new_state: SymbolState):
        self._state = new_state

    def can_transition_to(self, new_state: SymbolState) -> bool:
        valid_transitions = {
            SymbolState.IDLE: {SymbolState.PREPARING, SymbolState.STOPPED, SymbolState.ERROR},
            SymbolState.PREPARING: {SymbolState.PLACING_GRID, SymbolState.ERROR, SymbolState.STOPPED, SymbolState.IDLE},
            SymbolState.PLACING_GRID: {SymbolState.GRID_ACTIVE, SymbolState.ERROR, SymbolState.STOPPED, SymbolState.RESETTING},
            SymbolState.GRID_ACTIVE: {SymbolState.POSITIONS_ACTIVE, SymbolState.GRID_ACTIVE, SymbolState.ERROR, SymbolState.STOPPED, SymbolState.CLOSING},
            SymbolState.POSITIONS_ACTIVE: {SymbolState.TARGET_ACTIVE, SymbolState.LOCKED_EXPOSURE, SymbolState.CLOSING, SymbolState.ERROR, SymbolState.STOPPED},
            SymbolState.TARGET_PENDING: {SymbolState.TARGET_ACTIVE, SymbolState.ERROR, SymbolState.STOPPED},
            SymbolState.TARGET_ACTIVE: {SymbolState.CLOSING, SymbolState.LOCKED_EXPOSURE, SymbolState.POSITIONS_ACTIVE, SymbolState.ERROR, SymbolState.STOPPED},
            SymbolState.LOCKED_EXPOSURE: {SymbolState.TARGET_ACTIVE, SymbolState.POSITIONS_ACTIVE, SymbolState.CLOSING, SymbolState.ERROR, SymbolState.STOPPED},
            SymbolState.CLOSING: {SymbolState.RESETTING, SymbolState.ERROR, SymbolState.STOPPED},
            SymbolState.RESETTING: {SymbolState.PREPARING, SymbolState.ERROR, SymbolState.STOPPED},
            SymbolState.ERROR: {SymbolState.IDLE, SymbolState.STOPPED},
            SymbolState.STOPPED: {SymbolState.IDLE},
        }
        return new_state in valid_transitions.get(self._state, set())

    def transition_to(self, new_state: SymbolState) -> bool:
        if self.can_transition_to(new_state):
            self._state = new_state
            return True
        return False

    def is_active(self) -> bool:
        return self._state not in (SymbolState.IDLE, SymbolState.STOPPED, SymbolState.ERROR)

    def is_trading(self) -> bool:
        return self._state in (
            SymbolState.PLACING_GRID, SymbolState.GRID_ACTIVE,
            SymbolState.POSITIONS_ACTIVE, SymbolState.TARGET_ACTIVE,
            SymbolState.LOCKED_EXPOSURE,
        )

    def reset(self):
        self._state = SymbolState.IDLE
