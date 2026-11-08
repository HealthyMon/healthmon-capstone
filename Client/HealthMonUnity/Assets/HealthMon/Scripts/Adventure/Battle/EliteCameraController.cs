
using UnityEngine;

public class EliteCameraController : MonoBehaviour
{
    [Header("Camera Target")]
    [SerializeField] private Transform gridCenter;
    [SerializeField] private Transform enemy;

    [Header("Camera Settings")]
    [SerializeField]
    private Vector3 offset =
        new Vector3(0f, 4.5f, -7f);

    [SerializeField] private float lookHeight = 0.5f;

    private void Start()
    {
        SetupCamera();
    }

    public void SetupCamera()
    {
        if (gridCenter == null)
            return;

        // 카메라 위치 고정
        transform.position =
            gridCenter.position + offset;

        // 타일 중앙과 보스 사이를 바라봄
        Vector3 lookTarget =
            gridCenter.position + Vector3.up * lookHeight;

        if (enemy != null)
        {
            lookTarget = Vector3.Lerp(
                lookTarget,
                enemy.position + Vector3.up,
                0.25f
            );
        }

        transform.LookAt(lookTarget);
    }
}
