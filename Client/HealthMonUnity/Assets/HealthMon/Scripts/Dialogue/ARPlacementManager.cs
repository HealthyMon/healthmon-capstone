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
    public GameObject SpawnedHealthMon => spawnedHealthMon;
    private bool arMode, arPlaced;

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
        UpdatePetPresentation();
        if (!arMode) return;
        if (Touch.activeTouches.Count == 0)
            return;

        var touch = Touch.activeTouches[0];

        if (touch.phase != UnityEngine.InputSystem.TouchPhase.Began)
            return;

        Vector2 touchPosition = touch.screenPosition;

        if (UnityEngine.EventSystems.EventSystem.current != null)
        {
            var pointer = new UnityEngine.EventSystems.PointerEventData(UnityEngine.EventSystems.EventSystem.current)
                { position = touchPosition };
            var uiHits = new List<UnityEngine.EventSystems.RaycastResult>();
            UnityEngine.EventSystems.EventSystem.current.RaycastAll(pointer, uiHits);
            if (uiHits.Exists(hit => hit.module is UnityEngine.UI.GraphicRaycaster)) return;
        }

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

        PlaceAt(hits[0].pose);
    }

    public void SetARMode(bool enabled)
    {
        arMode = enabled;
        arPlaced = false;
    }

    // The home view follows the camera without requiring a detected AR plane.
    // Mobile AR still uses a real plane hit; desktop AR shows a labelled preview.
    private void UpdatePetPresentation()
    {
        if (!Healthmon.Common.CommonServerConnection.UsesServerAuthority) return;
        var connection = Healthmon.Common.CommonServerConnection.Instance;
        var model = Healthmon.Evolution.EvolutionClient.Instance?.Current;
        if (healthMonPrefab == null || connection == null ||
            !connection.IsConnected || connection.LatestState == null ||
            string.IsNullOrEmpty(connection.LatestState.model_reference) ||
            model == null || model.pet_id != connection.LatestState.pet_id)
        {
            if (spawnedHealthMon != null) spawnedHealthMon.SetActive(false);
            return;
        }
        if (arMode && Application.isMobilePlatform && !Application.isEditor)
        {
            if (spawnedHealthMon != null) spawnedHealthMon.SetActive(arPlaced);
            return;
        }
        var camera = Camera.main;
        if (camera == null || !camera.isActiveAndEnabled) return;
        var pose = new Pose(camera.transform.position + camera.transform.forward * 1.2f - camera.transform.up * .15f,
            Quaternion.LookRotation(camera.transform.forward, camera.transform.up));
        if (spawnedHealthMon == null) PlaceAt(pose);
        else
        {
            spawnedHealthMon.SetActive(true);
            spawnedHealthMon.transform.SetPositionAndRotation(pose.position, pose.rotation);
        }
    }

    // Shared by real AR raycasts and editor integration verification.
    public void PlaceAt(Pose hitPose)
    {
        arPlaced = true;

        if (spawnedHealthMon == null)
        {
            spawnedHealthMon = Instantiate(
                healthMonPrefab,
                hitPose.position,
                hitPose.rotation
            );

            Healthmon.Evolution.ArEvolutionModel.Attach(spawnedHealthMon);
            Debug.Log("[AR] TestHealthMon 생성 완료!");
        }
        else
        {
            spawnedHealthMon.SetActive(true);
            spawnedHealthMon.transform.SetPositionAndRotation(
                hitPose.position,
                hitPose.rotation
            );

            Debug.Log("[AR] TestHealthMon 위치 이동!");
        }
    }
}
