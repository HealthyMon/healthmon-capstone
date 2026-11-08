
public enum BattleActionType
{
    Attack,
    Skill,
    Item,
    Wait,
    Move
}

public enum EnemyActionType
{
    PhysicalAttack,
    MagicAttack
}

public enum BattleState
{
    Ready,
    Running,
    PlayerSelecting,
    ResolvingAction,
    Finished
}
