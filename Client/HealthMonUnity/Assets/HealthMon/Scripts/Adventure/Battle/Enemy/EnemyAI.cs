
using UnityEngine;

public class EnemyAI : MonoBehaviour
{
    [Header("몬스터")]
    public BattleUnit unit;

    [Header("다음 행동")]
    public EnemyActionType nextAction;

    public void Initialize()
    {
        SelectNextAction();
    }

    public void SelectNextAction()
    {
        int random = Random.Range(0, 2);

        nextAction = random == 0 ? EnemyActionType.PhysicalAttack:EnemyActionType.MagicAttack;
    }

    public string GetNextActionName()
    {
        switch (nextAction)
        {
            case EnemyActionType.PhysicalAttack:
                return "기본 공격";
            case EnemyActionType.MagicAttack:
                return "마법 공격";
            default:
                return "알 수 없음";
        }
    }
}
