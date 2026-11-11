
using UnityEngine;

public class EliteCameraController : MonoBehaviour
{
    [Header("Camera")]
    [SerializeField] private Camera targetCamera;

    [Header("Camera Target")]
    [SerializeField] private Transform gridCenter;
    [SerializeField] private Transform enemy;

    [Header("Camera Settings")]
    [SerializeField]
    private Vector3 offset =
        new Vector3(0f, 4.5f, -7f);

    [SerializeField] private float lookHeight = 0.5f;

    public void SetupCamera()
    {
        if (targetCamera == null || gridCenter == null)
        {
            Debug.LogWarning(
                "[EliteCamera] 카메라 또는 GridCenter 연결 누락"
            );
            return;
        }

        Transform cam = targetCamera.transform;

        cam.position = gridCenter.position + offset;

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

        cam.LookAt(lookTarget);

        Debug.Log(
            $"[EliteCamera] Position: {cam.position}, " +
            $"Target: {lookTarget}"
        );
    }
}
