
using System.Collections;
using UnityEngine;

public class BattleVisualController : MonoBehaviour
{
    [Header("시각 요소")]
    [SerializeField] private GameObject enemyVisual;
    [SerializeField] private Camera battleCamera;

    [Header("피격 연출")]
    [SerializeField] private float hitDuration = 0.25f;
    [SerializeField] private float hitDistance = 0.15f;

    [Header("카메라 흔들림")]
    [SerializeField] private float shakeDuration = 0.2f;
    [SerializeField] private float shakeAmount = 0.08f;

    private Vector3 enemyOriginalPosition;
    private Vector3 cameraOriginalPosition;

    private Coroutine hitCoroutine;
    private Coroutine shakeCoroutine;

    private void Awake()
    {
        if (enemyVisual != null)
            enemyOriginalPosition =
                enemyVisual.transform.localPosition;

        if (battleCamera != null)
            cameraOriginalPosition =
                battleCamera.transform.localPosition;
    }

    public void ResetVisuals()
    {
        if (hitCoroutine != null)
        {
            StopCoroutine(hitCoroutine);
            hitCoroutine = null;
        }

        if (shakeCoroutine != null)
        {
            StopCoroutine(shakeCoroutine);
            shakeCoroutine = null;
        }

        if (enemyVisual != null)
        {
            enemyVisual.SetActive(true);
            enemyVisual.transform.localPosition =
                enemyOriginalPosition;
        }

        if (battleCamera != null)
        {
            battleCamera.transform.localPosition =
                cameraOriginalPosition;
        }
    }
    public void SetEnemyVisual(GameObject newVisual)
    {
        // 기존 피격 애니메이션 중지
        if (hitCoroutine != null)
        {
            StopCoroutine(hitCoroutine);
            hitCoroutine = null;
        }

        enemyVisual = newVisual;

        if (enemyVisual != null)
        {
            enemyOriginalPosition =
                enemyVisual.transform.localPosition;
        }
    }


    public void PlayEnemyHit(bool strong)
    {
        if (enemyVisual == null) return;

        if (hitCoroutine != null)
            StopCoroutine(hitCoroutine);

        enemyVisual.transform.localPosition =
            enemyOriginalPosition;

        hitCoroutine = StartCoroutine(
            EnemyHitRoutine(strong)
        );
    }
    private IEnumerator EnemyHitRoutine(bool strong)
    {
        float elapsed = 0f;
        float distance = strong
            ? hitDistance * 2f
            : hitDistance;

        while (elapsed < hitDuration)
        {
            elapsed += Time.deltaTime;

            float progress =
                Mathf.Clamp01(elapsed / hitDuration);

            float offset =
                Mathf.Sin(progress * Mathf.PI * 4f)
                * distance
                * (1f - progress);

            enemyVisual.transform.localPosition =
                enemyOriginalPosition +
                new Vector3(offset, 0f, 0f);

            yield return null;
        }

        enemyVisual.transform.localPosition =
            enemyOriginalPosition;

        hitCoroutine = null;
    }
    public void PlayPlayerHit()
    {
        if (battleCamera == null) return;

        if (shakeCoroutine != null)
            StopCoroutine(shakeCoroutine);

        battleCamera.transform.localPosition =
            cameraOriginalPosition;

        shakeCoroutine = StartCoroutine(
            CameraShakeRoutine()
        );
    }
    private IEnumerator CameraShakeRoutine()
    {
        float elapsed = 0f;

        while (elapsed < shakeDuration)
        {
            elapsed += Time.deltaTime;

            float strength =
                1f - Mathf.Clamp01(
                    elapsed / shakeDuration
                );

            Vector2 offset =
                Random.insideUnitCircle
                * shakeAmount
                * strength;

            battleCamera.transform.localPosition =
                cameraOriginalPosition +
                new Vector3(offset.x, offset.y, 0f);

            yield return null;
        }

        battleCamera.transform.localPosition =
            cameraOriginalPosition;

        shakeCoroutine = null;
    }

    public void HideEnemy()
    {
        if (hitCoroutine != null)
        {
            StopCoroutine(hitCoroutine);
            hitCoroutine = null;
        }

        if (enemyVisual != null)
        {
            enemyVisual.transform.localPosition =
                enemyOriginalPosition;
            enemyVisual.SetActive(false);
        }
    }
}
