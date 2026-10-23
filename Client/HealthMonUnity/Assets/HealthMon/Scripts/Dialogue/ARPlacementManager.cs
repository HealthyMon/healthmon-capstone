using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.EnhancedTouch;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;
using Touch = UnityEngine.InputSystem.EnhancedTouch.Touch;

/// <summary>
/// On Android AR: UI taps do nothing in AR, creature taps interact,
/// and taps on a detected plane place/move the creature.
/// </summary>
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

    private GameObject spawnedHealthMon;
    private static readonly List<ARRaycastHit> hits = new List<ARRaycastHit>();
    private readonly List<RaycastResult> uiHits = new List<RaycastResult>();

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
        if (Touch.activeTouches.Count == 0) return;

        var touch = Touch.activeTouches[0];
        if (touch.phase != UnityEngine.InputSystem.TouchPhase.Began) return;

        Vector2 screenPosition = touch.screenPosition;

        // 1. Touching a UI graphic must not trigger AR interaction.
        if (IsPointerOverUI(screenPosition)) return;

        Camera cam = arCamera != null ? arCamera : Camera.main;
        if (cam == null)
        {
            Debug.LogError("[AR] AR Camera reference is missing.");
            return;
        }

        // 2. Did the user touch the already spawned character?
        if (spawnedHealthMon != null)
        {
            Ray ray = cam.ScreenPointToRay(screenPosition);
            if (Physics.Raycast(ray, out RaycastHit hit, 100f, ~0, QueryTriggerInteraction.Collide))
            {
                var reaction = hit.collider.GetComponentInParent<HealthMonTouchReaction>();
                if (reaction != null && reaction.gameObject == spawnedHealthMon)
                {
                    // Stop walking before the Happy touch reaction starts.
                    spawnedHealthMon.GetComponent<HealthMonMovement>()?.StopMoving();
                    reaction.OnCharacterTapped();
                    return;
                }
            }
        }

        // 3. Empty AR plane: place or move the character.
        if (raycastManager == null || healthMonPrefab == null)
        {
            Debug.LogError("[AR] RaycastManager or HealthMon Prefab not connected.");
            return;
        }

        if (!raycastManager.Raycast(screenPosition, hits, TrackableType.PlaneWithinPolygon))
            return;

        Pose pose = hits[0].pose;
        if (spawnedHealthMon == null)
        {
            spawnedHealthMon = Instantiate(healthMonPrefab, pose.position, pose.rotation);
            var reaction = spawnedHealthMon.GetComponent<HealthMonTouchReaction>();
            if (reaction != null)
                reaction.Initialize(petStateManager, questPrototype);
            else
                Debug.LogWarning("[AR] HealthMonTouchReaction is missing on prefab root.");
            Debug.Log("[AR] HealthMon created");
        }
        else
        {
            HealthMonMovement movement = spawnedHealthMon.GetComponent<HealthMonMovement>();
            if (movement != null)
            {
                movement.MoveTo(pose.position);
                Debug.Log("[AR] HealthMon walking to tapped plane");
            }
            else
            {
                Debug.LogWarning("[AR] HealthMonMovement missing; falling back to teleport.");
                spawnedHealthMon.transform.position = pose.position;
            }
        }
    }

    private bool IsPointerOverUI(Vector2 screenPosition)
    {
        if (EventSystem.current == null) return false;
        var pointer = new PointerEventData(EventSystem.current)
        {
            position = screenPosition
        };
        uiHits.Clear();
        EventSystem.current.RaycastAll(pointer, uiHits);
        return uiHits.Count > 0;
    }
}
