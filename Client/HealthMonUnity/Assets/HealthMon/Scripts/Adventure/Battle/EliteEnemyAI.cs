
using UnityEngine;

public enum EliteAttackType
{
    Normal,
    Horizontal,
    Vertical
}

public enum EliteAttackPhase
{
    None,
    Preparing
}

public class EliteEnemyAI : MonoBehaviour
{
    public EliteAttackType nextAttack { get; private set; }
    public EliteAttackPhase phase { get; private set; }

    // 가로 공격: 행 번호
    // 세로 공격: 열 번호
    public int targetIndex { get; private set; }

    public void Initialize()
    {
        phase = EliteAttackPhase.None;
        targetIndex = -1;
        SelectNextAttack();
    }

    public void SelectNextAttack()
    {
        nextAttack = (EliteAttackType)Random.Range(0, 3);
        targetIndex = -1;
    }


    public void PrepareSpecialAttack(Vector2Int playerCell)
    {
        if (nextAttack == EliteAttackType.Normal)
            return;

        switch (nextAttack)
        {
            case EliteAttackType.Horizontal:
                // 플레이어가 있는 행 선택
                targetIndex = playerCell.y;
                break;

            case EliteAttackType.Vertical:
                // 플레이어가 있는 열 선택
                targetIndex = playerCell.x;
                break;
        }

        phase = EliteAttackPhase.Preparing;
    }


    public void FinishPreparedAttack()
    {
        phase = EliteAttackPhase.None;
        SelectNextAttack();
    }

    public string GetNextActionName()
    {
        if (phase == EliteAttackPhase.Preparing)
        {
            return nextAttack == EliteAttackType.Horizontal
                ? $"가로 {GetRowName(targetIndex)} 공격 실행"
                : $"세로 {GetColumnName(targetIndex)} 공격 실행";
        }

        switch (nextAttack)
        {
            case EliteAttackType.Normal:
                return "일반 공격";

            case EliteAttackType.Horizontal:
                return "가로 특수 공격 준비";

            case EliteAttackType.Vertical:
                return "세로 특수 공격 준비";

            default:
                return "알 수 없음";
        }
    }

    public static string GetRowName(int row)
    {
        switch (row)
        {
            case 0: return "뒤";
            case 1: return "중앙";
            case 2: return "앞";
            default: return "알 수 없음";
        }
    }

    public static string GetColumnName(int col)
    {
        switch (col)
        {
            case 0: return "왼쪽";
            case 1: return "중앙";
            case 2: return "오른쪽";
            default: return "알 수 없음";
        }
    }
}
