
using System.Collections;
using TMPro;
using UnityEngine;

public class DamagePopupController : MonoBehaviour
{
    [Header("피해량 텍스트")]
    [SerializeField] private TMP_Text enemyDamageText;
    [SerializeField] private TMP_Text playerDamageText;

    [Header("연출 설정")]
    [SerializeField] private float duration = 0.7f;
    [SerializeField] private float moveDistance = 80f;

    private Coroutine enemyRoutine;
    private Coroutine playerRoutine;

    private void Awake()
    {
        enemyDamageText.gameObject.SetActive(false);
        playerDamageText.gameObject.SetActive(false);
    }

    public void ShowEnemyDamage(int damage)
    {
        if (enemyRoutine != null)
            StopCoroutine(enemyRoutine);

        enemyRoutine = StartCoroutine(
            ShowDamageRoutine(enemyDamageText, damage)
        );
    }

    public void ShowPlayerDamage(int damage)
    {
        if (playerRoutine != null)
            StopCoroutine(playerRoutine);

        playerRoutine = StartCoroutine(
            ShowDamageRoutine(playerDamageText, damage)
        );
    }

    private IEnumerator ShowDamageRoutine(
        TMP_Text target,
        int damage)
    {
        RectTransform rect =
            target.GetComponent<RectTransform>();

        Vector2 originalPosition =
            rect.anchoredPosition;

        Color originalColor = target.color;

        target.text = $"-{damage}";
        target.gameObject.SetActive(true);

        float elapsed = 0f;

        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;

            float t = Mathf.Clamp01(
                elapsed / duration
            );

            rect.anchoredPosition =
                originalPosition +
                Vector2.up * moveDistance * t;

            Color color = originalColor;
            color.a = 1f - t;
            target.color = color;

            yield return null;
        }

        rect.anchoredPosition = originalPosition;
        target.color = originalColor;
        target.gameObject.SetActive(false);
    }
}
