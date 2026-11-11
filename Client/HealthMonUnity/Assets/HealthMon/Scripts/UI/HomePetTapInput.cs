using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.UI;

/// <summary>
/// Home-only visual tap reaction for HealthMon_Slime.
/// Uses the project's new Input System for Editor mouse and Android touches.
/// Does not call ARInteraction quest logic or modify server-side pet stats.
/// Attach to HomePetAnchor, not to the original prefab asset.
/// </summary>
public sealed class HomePetTapInput : MonoBehaviour
{
    [Header("Scene references")]
    [SerializeField] private Camera homeCamera;
    [SerializeField] private GameObject homePanel;
    [SerializeField] private Collider petCollider;
    [SerializeField] private Animator petAnimator;

    [Header("Animation states (match HealthMon_Slime_Controller)")]
    [SerializeField] private string happyState = "Base Layer.Happy";
    [SerializeField] private string idleState = "Base Layer.Idle";
    [SerializeField, Min(0.1f)] private float happyDuration = 1.38f;
    [SerializeField, Min(0f)] private float tapCooldown = 1.6f;
    [SerializeField, Range(0f, 0.3f)] private float crossFadeSeconds = 0.08f;

    private readonly List<RaycastResult> uiResults = new List<RaycastResult>();
    private Coroutine returnRoutine;
    private float nextAllowedTap;

    private void Awake()
    {
        if (homeCamera == null) homeCamera = GetComponentInParent<Camera>();
        if (petCollider == null) petCollider = GetComponentInChildren<Collider>(true);
        if (petAnimator == null) petAnimator = GetComponentInChildren<Animator>(true);
    }

    private void Update()
    {
        if (homeCamera == null || !homeCamera.isActiveAndEnabled) return;
        if (homePanel != null && !homePanel.activeInHierarchy) return;
        if (Time.time < nextAllowedTap) return;

        Vector2 screenPosition;
        if (Touchscreen.current != null && Touchscreen.current.primaryTouch.press.wasPressedThisFrame)
        {
            screenPosition = Touchscreen.current.primaryTouch.position.ReadValue();
        }
        else if (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame)
        {
            screenPosition = Mouse.current.position.ReadValue();
        }
        else return;

        // Only real interactive UI controls block the tap.
        // Full-screen decorative HomePanel images may still receive UI raycasts.
        if (IsOverInteractiveUI(screenPosition)) return;
        if (petCollider == null || !petCollider.gameObject.activeInHierarchy) return;

        Ray ray = homeCamera.ScreenPointToRay(screenPosition);
        if (!petCollider.Raycast(ray, out _, 100f)) return;

        PlayHappy();
    }

    private bool IsOverInteractiveUI(Vector2 screenPosition)
    {
        if (EventSystem.current == null) return false;

        var eventData = new PointerEventData(EventSystem.current) { position = screenPosition };
        uiResults.Clear();
        EventSystem.current.RaycastAll(eventData, uiResults);
        foreach (var result in uiResults)
        {
            if (!(result.module is GraphicRaycaster)) continue;
            if (result.gameObject.GetComponentInParent<Selectable>() != null) return true;
            if (result.gameObject.GetComponentInParent<ScrollRect>() != null) return true;
        }
        return false;
    }

    private void PlayHappy()
    {
        if (petAnimator == null || !petAnimator.isActiveAndEnabled)
        {
            Debug.LogWarning("[HomePetTap] Animator is not assigned or enabled.");
            return;
        }
        if (!petAnimator.HasState(0, Animator.StringToHash(happyState)))
        {
            Debug.LogWarning("[HomePetTap] Happy state is missing: " + happyState);
            return;
        }

        nextAllowedTap = Time.time + Mathf.Max(tapCooldown, happyDuration);
        if (returnRoutine != null) StopCoroutine(returnRoutine);
        petAnimator.CrossFadeInFixedTime(happyState, crossFadeSeconds, 0, 0f);
        returnRoutine = StartCoroutine(ReturnToIdle());
        Debug.Log("[HomePetTap] HomePet touched -> Happy");
    }

    private IEnumerator ReturnToIdle()
    {
        yield return new WaitForSeconds(happyDuration);
        if (petAnimator != null && petAnimator.isActiveAndEnabled &&
            petAnimator.HasState(0, Animator.StringToHash(idleState)))
        {
            petAnimator.CrossFadeInFixedTime(idleState, crossFadeSeconds, 0, 0f);
        }
        returnRoutine = null;
    }

    private void OnDisable()
    {
        if (returnRoutine != null) StopCoroutine(returnRoutine);
        returnRoutine = null;
    }
}
