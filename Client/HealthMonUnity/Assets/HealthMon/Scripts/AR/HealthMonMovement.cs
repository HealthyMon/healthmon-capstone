using System.Collections;
using UnityEngine;

/// <summary>
/// Moves the AR pet smoothly toward a detected AR plane position.
/// Put this component on the root of the HealthMon_Slime prefab variant.
/// </summary>
public class HealthMonMovement : MonoBehaviour
{
    [Header("Movement (meters per second)")]
    [SerializeField, Min(0.01f)] private float moveSpeed = 0.35f;
    [SerializeField, Min(0f)] private float stoppingDistance = 0.03f;
    [SerializeField, Min(0f)] private float turnSpeedDegrees = 360f;
    [SerializeField] private float modelForwardOffsetDegrees = 0f;

    [Header("Animator")]
    [SerializeField] private Animator animator;
    [SerializeField] private string moveStateName = "Base Layer.Move";
    [SerializeField] private string idleStateName = "Base Layer.Idle";
    [SerializeField, Range(0f, 0.3f)] private float crossFadeSeconds = 0.08f;

    private Coroutine movementRoutine;
    private bool isMoving;

    private void Awake()
    {
        if (animator == null)
            animator = GetComponentInChildren<Animator>(true);
    }

    public void MoveTo(Vector3 worldPosition)
    {
        StopMoving();
        movementRoutine = StartCoroutine(MoveRoutine(worldPosition));
    }

    public void UseAnimator(Animator modelAnimator)
    {
        StopMoving();
        animator = modelAnimator;
    }

    public void StopMoving()
    {
        if (movementRoutine != null)
        {
            StopCoroutine(movementRoutine);
            movementRoutine = null;
        }
        if (isMoving)
        {
            isMoving = false;
            PlayState(idleStateName);
        }
    }

    private IEnumerator MoveRoutine(Vector3 destination)
    {
        if (Vector3.Distance(transform.position, destination) <= stoppingDistance)
        {
            movementRoutine = null;
            yield break;
        }

        isMoving = true;
        PlayState(moveStateName);

        while (Vector3.Distance(transform.position, destination) > stoppingDistance)
        {
            Vector3 direction = destination - transform.position;
            direction.y = 0f;
            if (direction.sqrMagnitude > 0.0001f)
            {
                Quaternion facing = Quaternion.LookRotation(direction.normalized, Vector3.up)
                                    * Quaternion.Euler(0f, modelForwardOffsetDegrees, 0f);
                transform.rotation = Quaternion.RotateTowards(
                    transform.rotation, facing, turnSpeedDegrees * Time.deltaTime);
            }

            transform.position = Vector3.MoveTowards(
                transform.position, destination, moveSpeed * Time.deltaTime);
            yield return null;
        }

        transform.position = destination;
        isMoving = false;
        movementRoutine = null;
        PlayState(idleStateName);
    }

    private void PlayState(string fullName)
    {
        if (animator == null) return;
        int hash = Animator.StringToHash(fullName);
        if (animator.HasState(0, hash))
            animator.CrossFadeInFixedTime(fullName, crossFadeSeconds, 0, 0f);
        else
            Debug.LogWarning("[HealthMonMovement] Animator state not found: " + fullName);
    }

    private void OnDisable()
    {
        StopMoving();
    }
}
