using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class AdventureMainMenu : MonoBehaviour
{
    [SerializeField] private TMP_Text difficultyText;
    [SerializeField] private TMP_Text regionText;
    [SerializeField] private Button continueButton;
    [SerializeField] private Button normalButton;
    [SerializeField] private Button hardButton;
    [SerializeField] private string loadingSceneName = "AdventureLoadingScene";

    private AdventureLaunchSettings.Difficulty difficulty = AdventureLaunchSettings.Difficulty.Easy;
    private AdventureLaunchSettings.Region region = AdventureLaunchSettings.Region.Entrance;
    private bool isStarting;

    private void Start()
    {
        // 이미 생성된 메인 씬에도 적용되도록 이름으로 버튼을 보완 탐색한다.
        if (continueButton == null) continueButton = FindButton("Region_Checkpoint");
        if (normalButton == null) normalButton = FindButton("Difficulty_1");
        if (hardButton == null) hardButton = FindButton("Difficulty_2");
        if (normalButton != null) normalButton.interactable = false;
        if (hardButton != null) hardButton.interactable = false;
        Refresh();
    }

    private Button FindButton(string objectName)
    {
        foreach (var button in GetComponentsInChildren<Button>(true))
            if (button.gameObject.name == objectName) return button;
        return null;
    }

    public void SelectDifficulty(int index)
    {
        if (isStarting || index != 0) return; // 당장은 쉬움 난이도만 지원
        difficulty = AdventureLaunchSettings.Difficulty.Easy;
        Refresh();
    }

    public void SelectRegion(int index)
    {
        if (isStarting || index < 0 || index > 1) return;
        if (index == 1 && !HasCheckpoint()) return;
        region = (AdventureLaunchSettings.Region)index;
        Refresh();
    }

    public void StartAdventure()
    {
        if (isStarting) return;
        if (region == AdventureLaunchSettings.Region.Checkpoint && !HasCheckpoint())
        {
            region = AdventureLaunchSettings.Region.Entrance;
            Refresh();
            Debug.LogWarning("[AdventureMainMenu] 저장 기록을 불러올 수 없어 이어서 하기를 취소했습니다.");
            return;
        }
        if (!Application.CanStreamedLevelBeLoaded(loadingSceneName))
        {
            Debug.LogError("[AdventureMainMenu] Build Settings에 로딩 씬이 없습니다: " + loadingSceneName);
            return;
        }

        isStarting = true;
        AdventureLaunchSettings.Prepare(difficulty, region);
        SceneManager.LoadScene(loadingSceneName);
    }

    private void Refresh()
    {
        bool hasCheckpoint = HasCheckpoint();
        if (!hasCheckpoint && region == AdventureLaunchSettings.Region.Checkpoint)
            region = AdventureLaunchSettings.Region.Entrance;
        if (continueButton != null) continueButton.interactable = hasCheckpoint && !isStarting;
        if (continueButton != null)
        {
            var label = continueButton.GetComponentInChildren<TMP_Text>(true);
            if (label != null) label.text = "이어서 하기";
        }
        if (difficultyText != null)
        {
            switch (difficulty)
            {
                case AdventureLaunchSettings.Difficulty.Easy: difficultyText.text = "난이도: 쉬움"; break;
                case AdventureLaunchSettings.Difficulty.Hard: difficultyText.text = "난이도: 어려움"; break;
                default: difficultyText.text = "난이도: 보통"; break;
            }
        }
        if (regionText != null)
            regionText.text = region == AdventureLaunchSettings.Region.Entrance
                ? "시작 지역: 입구 (새로 시작)" : "시작 지역: 저장된 체크포인트 (이어서 하기)";

        // 구 버전 에디터 빌더로 생성된 씬의 안내 문구도 자동 갱신한다.
        var note = transform.Find("Note");
        if (note != null)
        {
            var text = note.GetComponent<TMP_Text>();
            if (text != null)
                text.text = "※ 현재 쉬움만 선택 가능합니다. 저장 기록이 있을 때 이어서 하기가 활성화됩니다.";
        }
    }

    private static bool HasCheckpoint() => AdventureSaveSystem.TryLoad(out _);
}
