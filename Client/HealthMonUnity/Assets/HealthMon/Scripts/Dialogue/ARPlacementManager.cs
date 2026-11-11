
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;
using UnityEngine.InputSystem.EnhancedTouch;

using Touch = UnityEngine.InputSystem.EnhancedTouch.Touch;

public class ARPlacementManager : MonoBehaviour
{
    [Header("AR")]
    [SerializeField] private ARRaycastManager raycastManager;
    [SerializeField] private Camera arCamera;

    [Header("Character")]
    [SerializeField] private GameObject healthMonPrefab;

    [Header("Managers")]
    [SerializeField] private PetStateManager petStateManager;
    [SerializeField] private QuestPrototype questPrototype;

    // 현재 생성된 AR 헬스몬
    private GameObject spawnedHealthMon;

    public GameObject SpawnedHealthMon => spawnedHealthMon;

    // ★ 추가: 말풍선에서 캐릭터 Transform 접근
    public Transform CurrentHealthMonTransform
    {
        get
        {
            return spawnedHealthMon != null
                ? spawnedHealthMon.transform
                : null;
        }
    }

    private bool arMode;
    private bool arPlaced;

    // ★ 캐릭터 배치 및 이동 이벤트
    public event Action<Transform> OnHealthMonPlaced;

    private static readonly List<ARRaycastHit> hits =
        new List<ARRaycastHit>();

    private readonly List<RaycastResult> uiHits =
        new List<RaycastResult>();

    // ==================================================
    // Enhanced Touch
    // ==================================================

    private void OnEnable()
    {
        EnhancedTouchSupport.Enable();
    }

    private void OnDisable()
    {
        EnhancedTouchSupport.Disable();
    }

    // ==================================================
    // Update
    // ==================================================

    private void Update()
    {
        UpdatePetPresentation();

        if (!arMode)
            return;

        if (Touch.activeTouches.Count == 0)
            return;

        var touch = Touch.activeTouches[0];

        if (touch.phase !=
            UnityEngine.InputSystem.TouchPhase.Began)
            return;

        Vector2 touchPosition = touch.screenPosition;

        // UI를 터치한 경우 AR 배치 방지
        if (EventSystem.current != null)
        {
            var pointer =
                new PointerEventData(EventSystem.current)
                {
                    position = touchPosition
                };

            uiHits.Clear();

            EventSystem.current.RaycastAll(
                pointer,
                uiHits
            );

            if (uiHits.Exists(
                hit => hit.module is UnityEngine.UI.GraphicRaycaster))
                return;
        }

        Camera camera =
            arCamera != null ? arCamera : Camera.main;

        if (camera == null)
            return;

        // ==================================================
        // 기존 캐릭터 터치 반응
        // ==================================================

        if (spawnedHealthMon != null &&
            spawnedHealthMon.activeInHierarchy &&
            Physics.Raycast(
                camera.ScreenPointToRay(touchPosition),
                out RaycastHit creatureHit,
                100f,
                ~0,
                QueryTriggerInteraction.Collide))
        {
            var reaction =
                creatureHit.collider
                    .GetComponentInParent<HealthMonTouchReaction>();

            if (reaction != null &&
                reaction.gameObject == spawnedHealthMon)
            {
                spawnedHealthMon
                    .GetComponent<HealthMonMovement>()
                    ?.StopMoving();

                reaction.OnCharacterTapped();

                return;
            }
        }

        if (raycastManager == null ||
            healthMonPrefab == null)
            return;

        Debug.Log(
            "[AR] 화면 터치 감지: " + touchPosition
        );

        // ==================================================
        // AR 평면 Raycast
        // ==================================================

        bool hitPlane = raycastManager.Raycast(
            touchPosition,
            hits,
            TrackableType.PlaneWithinPolygon
        );

        if (!hitPlane)
        {
            Debug.LogWarning(
                "[AR] 터치는 감지했지만 AR 평면을 찾지 못했습니다."
            );

            return;
        }

        Debug.Log("[AR] AR 평면 Raycast 성공!");

        // 이미 캐릭터가 있다면 이동
        if (spawnedHealthMon != null &&
            arPlaced &&
            spawnedHealthMon
                .GetComponent<HealthMonMovement>() != null)
        {
            spawnedHealthMon
                .GetComponent<HealthMonMovement>()
                .MoveTo(hits[0].pose.position);
        }
        else
        {
            PlaceAt(hits[0].pose);
        }
    }

    // ==================================================
    // AR 모드 활성화 / 비활성화
    // ==================================================

    public void SetARMode(bool enabled)
    {
        arMode = enabled;
        arPlaced = false;

        if (spawnedHealthMon != null)
        {
            if (!enabled)
            {
                spawnedHealthMon
                    .GetComponent<HealthMonMovement>()
                    ?.StopMoving();
            }

            spawnedHealthMon.SetActive(false);
        }
    }

    // ==================================================
    // PC Editor 미리보기 / 실제 AR 표시
    // ==================================================

    private void UpdatePetPresentation()
    {
        // 홈 또는 AR이 아닌 화면에서는 숨김
        if (!arMode)
        {
            if (spawnedHealthMon != null &&
                spawnedHealthMon.activeSelf)
            {
                spawnedHealthMon.SetActive(false);
            }

            return;
        }

        if (healthMonPrefab == null)
            return;

        // ==================================================
        // Unity Editor: 카메라 앞에 캐릭터 표시
        // ==================================================

        if (Application.isEditor)
        {
            Camera camera =
                arCamera != null ? arCamera : Camera.main;

            if (camera == null ||
                !camera.isActiveAndEnabled)
                return;

            var preview = new Pose(
                camera.transform.position
                    + camera.transform.forward * 1.2f
                    - camera.transform.up * 0.15f,

                Quaternion.LookRotation(
                    -camera.transform.forward,
                    camera.transform.up
                )
            );

            if (spawnedHealthMon == null)
            {
                PlaceAt(preview);
            }
            else
            {
                spawnedHealthMon.SetActive(true);

                spawnedHealthMon.transform
                    .SetPositionAndRotation(
                        preview.position,
                        preview.rotation
                    );
            }
        }

        // ==================================================
        // Android: 평면 터치 후 캐릭터 표시
        // ==================================================

        else if (spawnedHealthMon != null && !arPlaced)
        {
            spawnedHealthMon.SetActive(false);
        }
    }

    // ==================================================
    // 캐릭터 생성 / 배치
    // ==================================================

    public void PlaceAt(Pose hitPose)
    {
        arPlaced = true;

        // 실제 AR에서는 사용자를 바라보도록 회전
        if (!Application.isEditor && arCamera != null)
        {
            Vector3 towardCamera =
                arCamera.transform.position - hitPose.position;

            towardCamera.y = 0f;

            if (towardCamera.sqrMagnitude > 0.0001f)
            {
                hitPose.rotation =
                    Quaternion.LookRotation(
                        towardCamera.normalized,
                        Vector3.up
                    );
            }
        }

        // ==================================================
        // 처음 생성
        // ==================================================

        if (spawnedHealthMon == null)
        {
            spawnedHealthMon = Instantiate(
                healthMonPrefab,
                hitPose.position,
                hitPose.rotation
            );

            // 기존 진화 모델 연결
            Healthmon.Evolution.ArEvolutionModel.Attach(
                spawnedHealthMon
            );

            // 기존 터치 반응 연결
            var reaction =
                spawnedHealthMon
                    .GetComponent<HealthMonTouchReaction>();

            if (reaction != null)
            {
                reaction.Initialize(
                    petStateManager != null
                        ? petStateManager
                        : FindAnyObjectByType<PetStateManager>(),

                    questPrototype != null
                        ? questPrototype
                        : FindAnyObjectByType<QuestPrototype>(
                            FindObjectsInactive.Include
                        )
                );
            }

            Debug.Log("[AR] HealthMon 생성 완료!");
        }

        // ==================================================
        // 기존 캐릭터 재배치
        // ==================================================

        else
        {
            spawnedHealthMon.SetActive(true);

            spawnedHealthMon.transform
                .SetPositionAndRotation(
                    hitPose.position,
                    hitPose.rotation
                );

            Debug.Log("[AR] HealthMon 위치 이동!");
        }

        // ==================================================
        // ★ 추가: 말풍선 시스템에 캐릭터 위치 전달
        // ==================================================

        if (spawnedHealthMon != null)
        {
            OnHealthMonPlaced?.Invoke(
                spawnedHealthMon.transform
            );

            Debug.Log(
                "[AR] 말풍선 타겟 연결 이벤트 전달 완료!"
            );
        }
    }
}
