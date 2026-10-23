using System.Collections;
using UnityEngine;

/// <summary>
/// Receives character taps from ARPlacementManager.
/// Plays Happy once and returns to Idle, while updating pet stats and AR quest.
/// Attach to the root of the HealthMon_Slime prefab variant.
/// </summary>
public class HealthMonTouchReaction : MonoBehaviour
{
    [Header("Visual feedback (fallback without Animator)")]
    [SerializeField] private Transform visualRoot;
    [SerializeField, Range(0.05f, 0.5f)] private float pulseAmount = 0.15f;
    [SerializeField, Min(0.05f)] private float pulseDuration = 0.35f;
    [SerializeField, Min(0f)] private float tapCooldown = 1.6f;

    [Header("Animation")]
    [SerializeField] private Animator animator;
    [SerializeField] private string happyStateName = "Base Layer.Happy";
    [SerializeField] private string idleStateName = "Base Layer.Idle";
    [SerializeField, Min(0.1f)] private float happyReturnDelay = 1.38f;
    [SerializeField, Range(0f, 0.3f)] private float crossFadeTime = 0.08f;

    [Header("Game effects")]
    [SerializeField, Min(0)] private int intimacyPerTap = 2;

    private PetStateManager petStateManager;
    private QuestPrototype questPrototype;
    private Vector3 originalScale;
    private Coroutine visualRoutine;
    private float nextTapTime;

    private void Awake()
    {
        if (visualRoot == null) visualRoot = transform;
        if (animator == null) animator = GetComponentInChildren<Animator>(true);
        originalScale = visualRoot.localScale;
    }

    public void Initialize(PetStateManager petState, QuestPrototype quest)
    {
        petStateManager = petState;
        questPrototype = quest;
    }

    public void UseVisual(Transform model)
    {
        if (visualRoutine != null) StopCoroutine(visualRoutine);
        visualRoutine = null;
        if (visualRoot != null) visualRoot.localScale = originalScale;
        visualRoot = model;
        originalScale = model.localScale;
        animator = model.GetComponentInChildren<Animator>(true);
    }

    public void OnCharacterTapped()
    {
        if (Time.time < nextTapTime) return;
        nextTapTime = Time.time + Mathf.Max(tapCooldown, happyReturnDelay + 0.12f);

        if (visualRoutine != null)
        {
            StopCoroutine(visualRoutine);
            visualRoutine = null;
        }

        if (animator != null && animator.isActiveAndEnabled && animator.HasState(0, Animator.StringToHash(happyStateName)))
        {
            animator.CrossFadeInFixedTime(happyStateName, crossFadeTime, 0, 0f);
            visualRoutine = StartCoroutine(ReturnToIdle());
        }
        else
        {
            Debug.LogWarning("[HealthMonTouch] Happy state not found; playing pulse instead.");
            visualRoutine = StartCoroutine(Pulse());
        }

        if (petStateManager != null)
            petStateManager.AddIntimacy(intimacyPerTap);
        else
            Debug.LogWarning("[HealthMonTouch] PetStateManager not connected");

        if (questPrototype != null)
            questPrototype.AddARInteraction();
        else
            Debug.LogWarning("[HealthMonTouch] QuestPrototype not connected");

        Debug.Log(Healthmon.Common.CommonServerConnection.UsesServerAuthority ?
            "[HealthMonTouch] Pet touch visual reaction; common-server state retained." :
            "[HealthMonTouch] Happy reaction / intimacy +" + intimacyPerTap + " / AR quest +1");
    }

    private IEnumerator ReturnToIdle()
    {
        yield return new WaitForSeconds(happyReturnDelay);
        if (animator != null && animator.HasState(0, Animator.StringToHash(idleStateName)))
            animator.CrossFadeInFixedTime(idleStateName, crossFadeTime, 0, 0f);
        else
            Debug.LogWarning("[HealthMonTouch] Idle state not found");
        visualRoutine = null;
    }

    private IEnumerator Pulse()
    {
        float elapsed = 0f;
        while (elapsed < pulseDuration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / pulseDuration);
            float scale = 1f + Mathf.Sin(t * Mathf.PI) * pulseAmount;
            if (visualRoot != null) visualRoot.localScale = originalScale * scale;
            yield return null;
        }
        if (visualRoot != null) visualRoot.localScale = originalScale;
        visualRoutine = null;
    }

    private void OnDisable()
    {
        if (visualRoutine != null)
        {
            StopCoroutine(visualRoutine);
            visualRoutine = null;
        }
        if (visualRoot != null) visualRoot.localScale = originalScale;
    }
}
