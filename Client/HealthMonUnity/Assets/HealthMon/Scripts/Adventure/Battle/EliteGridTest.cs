
using UnityEngine;
using UnityEngine.InputSystem;

public class EliteGridTest : MonoBehaviour
{
    [SerializeField] private EliteGridManager grid;

    private void Update()
    {
        Keyboard keyboard = Keyboard.current;

        if (keyboard == null)
            return;

        // 1: 가로 중앙 공격
        if (keyboard.digit1Key.wasPressedThisFrame)
        {
            grid.ShowRowWarning(1);
        }

        // 2: 세로 중앙 공격
        if (keyboard.digit2Key.wasPressedThisFrame)
        {
            grid.ShowColumnWarning(1);
        }

        // 3: 중앙 한 칸 공격
        if (keyboard.digit3Key.wasPressedThisFrame)
        {
            grid.ShowSingleWarning(
                new Vector2Int(1, 1)
            );
        }

        // 0: 경고 초기화
        if (keyboard.digit0Key.wasPressedThisFrame)
        {
            grid.ClearWarnings();
        }
    }
}
