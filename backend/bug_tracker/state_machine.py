"""Bug 状态机：定义合法的状态流转与校验"""

# 状态流转表：from_status -> set(allowed to_status)
BUG_TRANSITIONS = {
    'new':        {'confirmed', 'rejected', 'assigned'},
    'confirmed':  {'assigned', 'rejected'},
    'assigned':   {'fixing', 'rejected'},
    'fixing':     {'fixed', 'rejected'},
    'fixed':      {'verifying'},
    'verifying':  {'closed', 'reopened'},
    'reopened':   {'assigned', 'fixing'},
    'closed':     {'reopened'},
    'rejected':   {'reopened'},
}

# 进入这些状态时应自动设置 closed_at
TERMINAL_STATUSES = {'closed', 'rejected'}


class TransitionError(Exception):
    """非法状态流转异常"""

    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        allowed = BUG_TRANSITIONS.get(from_status, set())
        msg = (
            f'不能从 "{from_status}" 流转到 "{to_status}"。'
            f'当前状态允许的目标: {sorted(allowed) or "无（终态需先 reopen）"}'
        )
        super().__init__(msg)


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in BUG_TRANSITIONS.get(from_status, set())


def validate_transition(from_status: str, to_status: str) -> None:
    """校验流转合法性，非法则抛 TransitionError"""
    if from_status == to_status:
        raise TransitionError(from_status, to_status)
    if not can_transition(from_status, to_status):
        raise TransitionError(from_status, to_status)


def allowed_next_statuses(from_status: str) -> list:
    """返回当前状态可流转的下一状态列表（用于前端按钮渲染）"""
    return sorted(BUG_TRANSITIONS.get(from_status, set()))
