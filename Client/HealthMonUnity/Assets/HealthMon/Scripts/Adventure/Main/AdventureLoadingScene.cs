using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class AdventureLoadingScene : MonoBehaviour
{
    [SerializeField] private string adventureSceneName = "AdventureScene";
    [SerializeField, Min(0f)] private float minimumDisplaySeconds = 1.2f;
    [SerializeField] private Slider progressBar;
    [SerializeField] private TMP_Text progressText;
    [SerializeField] private TMP_Text loadingMessage;

    private void Start() => StartCoroutine(LoadAdventure());

    private IEnumerator LoadAdventure()
    {
        if (progressBar != null) progressBar.value = 0f;
        if (loadingMessage != null) loadingMessage.text = "탐험을 준비하고 있습니다...";
        if (!AdventureLaunchSettings.HasPendingLaunch)
        {
            Debug.LogWarning("[AdventureLoadingScene] 메인 씬에서 전달된 시작 요청이 없습니다.");
            AdventureLaunchSettings.Prepare(AdventureLaunchSettings.Difficulty.Normal,
                AdventureLaunchSettings.Region.Entrance);
        }

        // 추후 이 위치에 성장 스탯 변환, 대사 생성, 저장 데이터 검증을 연결합니다.
        // 실제 작업 완료 전에는 탐험 씬 활성화를 허용하지 않도록 확장할 수 있습니다.
        if (!Application.CanStreamedLevelBeLoaded(adventureSceneName))
        {
            Debug.LogError("[AdventureLoadingScene] Build Settings에 탐험 씬이 없습니다: " + adventureSceneName);
            if (loadingMessage != null) loadingMessage.text = "탐험 씬을 찾을 수 없습니다.";
            yield break;
        }

        var operation = SceneManager.LoadSceneAsync(adventureSceneName);
        if (operation == null) yield break;
        operation.allowSceneActivation = false;
        float timer = 0f;
        while (operation.progress < 0.9f || timer < minimumDisplaySeconds)
        {
            timer += Time.unscaledDeltaTime;
            float loadFraction = Mathf.Clamp01(operation.progress / 0.9f);
            float timeFraction = minimumDisplaySeconds <= 0f ? 1f : Mathf.Clamp01(timer / minimumDisplaySeconds);
            float progress = Mathf.Min(loadFraction, timeFraction);
            if (progressBar != null) progressBar.value = progress;
            if (progressText != null) progressText.text = Mathf.RoundToInt(progress * 100f) + "%";
            yield return null;
        }

        if (progressBar != null) progressBar.value = 1f;
        if (progressText != null) progressText.text = "100%";
        operation.allowSceneActivation = true;
    }
}
