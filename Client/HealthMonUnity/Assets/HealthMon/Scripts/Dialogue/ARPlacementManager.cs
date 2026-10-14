using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

using UnityEngine.InputSystem.EnhancedTouch;
using Touch = UnityEngine.InputSystem.EnhancedTouch.Touch;

public class ARPlacementManager : MonoBehaviour
{
    [Header("AR")]
    [SerializeField] private ARRaycastManager raycastManager;

    [Header("Character")]
    [SerializeField] private GameObject healthMonPrefab;

    private GameObject spawnedHealthMon;

    private static readonly List<ARRaycastHit> hits =
        new List<ARRaycastHit>();

    private void OnEnable()
    {
        EnhancedTouchSupport.Enable();
    }

    private void OnDisable()
    {
        EnhancedTouchSupport.Disable();
    }

    private void Update()
    {
        if (Touch.activeTouches.Count == 0)
            return;

        var touch = Touch.activeTouches[0];

        if (touch.phase != UnityEngine.InputSystem.TouchPhase.Began)
            return;

        Vector2 touchPosition = touch.screenPosition;

        Debug.Log("[AR] 화면 터치 감지: " + touchPosition);

        bool hitPlane = raycastManager.Raycast(
            touchPosition,
            hits,
            TrackableType.PlaneWithinPolygon
        );

        if (!hitPlane)
        {
            Debug.LogWarning("[AR] 터치는 감지했지만 AR 평면을 찾지 못했습니다.");
            return;
        }

        Debug.Log("[AR] AR 평면 Raycast 성공!");

        Pose hitPose = hits[0].pose;

        if (spawnedHealthMon == null)
        {
            spawnedHealthMon = Instantiate(
                healthMonPrefab,
                hitPose.position,
                hitPose.rotation
            );

            Debug.Log("[AR] TestHealthMon 생성 완료!");
        }
        else
        {
            spawnedHealthMon.transform.SetPositionAndRotation(
                hitPose.position,
                hitPose.rotation
            );

            Debug.Log("[AR] TestHealthMon 위치 이동!");
        }
    }
}