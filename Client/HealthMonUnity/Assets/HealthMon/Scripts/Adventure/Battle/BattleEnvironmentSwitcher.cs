using UnityEngine;

/// <summary>전투별 배경을 교체한다. 카메라, 타일, 전투 로직은 건드리지 않는다.</summary>
public class BattleEnvironmentSwitcher : MonoBehaviour
{
    [SerializeField] private GameObject normalEnvironment;
    [SerializeField] private GameObject eliteEnvironment;

    public void SetMode(bool elite)
    {
        if (normalEnvironment != null) normalEnvironment.SetActive(!elite);
        if (eliteEnvironment != null) eliteEnvironment.SetActive(elite);
    }

    public void Hide()
    {
        if (normalEnvironment != null) normalEnvironment.SetActive(false);
        if (eliteEnvironment != null) eliteEnvironment.SetActive(false);
    }
}
