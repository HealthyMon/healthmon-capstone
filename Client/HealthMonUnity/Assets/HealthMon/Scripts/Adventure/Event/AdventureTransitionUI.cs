
using System;
using System.Collections;
using UnityEngine;
using TMPro;
using UnityEngine.UI;

public class AdventureTransitionUI : MonoBehaviour
{
    [Header("Content")]
    [SerializeField] private GameObject descendContent;
    [SerializeField] private GameObject battleIntroContent;

    [Header("Dialogue")]
    [SerializeField] private AdventureDialogueManager dialogueManager;

    [Header("Duration")]
    [SerializeField, Min(0.1f)]
    private float descendDuration = 1.8f;

    [SerializeField, Min(0.1f)]
    private float battleDuration = 1.2f;

    public bool IsPlaying { get; private set; }
    public UISpriteSequence ActiveSequence { get; private set; }
    private GameObject fullscreen;
    private TMP_Text caption;

    private void Awake()
    {
        HideAll();
    }

    private void EnsureFullscreen()
    {
        if (fullscreen != null) return;
        var source = battleIntroContent != null ? battleIntroContent : descendContent;
        if (source == null) return;
        var root = source.GetComponentInParent<Canvas>().rootCanvas;
        fullscreen = new GameObject("AdventureTransitionFullscreen", typeof(RectTransform), typeof(Canvas), typeof(GraphicRaycaster));
        fullscreen.transform.SetParent(root.transform, false);
        HealthMonUILayout.Place((RectTransform)fullscreen.transform, 0, 0, 1, 1);
        var canvas = fullscreen.GetComponent<Canvas>();
        canvas.overrideSorting = true;
        canvas.sortingOrder = 500;
        foreach (var content in new[] { descendContent, battleIntroContent })
        {
            if (content == null) continue;
            content.transform.SetParent(fullscreen.transform, false);
            HealthMonUILayout.Place((RectTransform)content.transform, 0, 0, 1, 1);
            content.transform.localScale = Vector3.one;
            var image = content.GetComponent<Image>();
            image.preserveAspect = false;
            image.raycastTarget = true;
            image.color = Color.white;
            content.AddComponent<AdventureTransitionImage>().preserveCreature = content == battleIntroContent;
        }
        var band = new GameObject("TransitionCaption", typeof(RectTransform), typeof(Image));
        band.transform.SetParent(fullscreen.transform, false);
        HealthMonUILayout.Place((RectTransform)band.transform, .07f, .09f, .93f, .17f);
        band.GetComponent<Image>().color = new Color(.06f, .025f, .015f, .82f);
        var label = new GameObject("Label", typeof(RectTransform), typeof(TextMeshProUGUI));
        label.transform.SetParent(band.transform, false);
        caption = label.GetComponent<TMP_Text>();
        var original = root.transform.Find("AdventureHUD/EventDescription")?.GetComponent<TMP_Text>();
        if (original != null) caption.font = original.font;
        HealthMonUILayout.Text(caption, .04f, .12f, .96f, .88f, 44);
        caption.alignment = TextAlignmentOptions.Center;
        caption.color = new Color(1, .86f, .57f);
        caption.raycastTarget = false;
        fullscreen.SetActive(false);
    }

    public void PlayDescend(Action onComplete)
    {
        Play(
            descendContent,
            AdventureDialogueType.Descending,
            descendDuration,
            onComplete
        );
    }

    public void PlayBattleIntro(bool isElite, Action onComplete)
    {
        AdventureDialogueType type = isElite
            ? AdventureDialogueType.EliteBattle
            : AdventureDialogueType.Battle;

        Play(
            battleIntroContent,
            type,
            battleDuration,
            onComplete
        );
    }

    private void Play(
        GameObject content,
        AdventureDialogueType dialogue,
        float duration,
        Action onComplete)
    {
        if (IsPlaying)
        {
            Debug.LogWarning(
                "[Adventure] 다른 연출이 재생 중입니다."
            );
            return;
        }

        StartCoroutine(
            PlayRoutine(content, dialogue, duration, onComplete)
        );
    }

    private IEnumerator PlayRoutine(
        GameObject content,
        AdventureDialogueType dialogue,
        float duration,
        Action onComplete)
    {
        IsPlaying = true;

        EnsureFullscreen();
        HideAll();

        if (fullscreen != null) fullscreen.SetActive(true);
        if (caption != null) caption.text = dialogue == AdventureDialogueType.Descending
            ? "다음 층으로 이동 중" : dialogue == AdventureDialogueType.EliteBattle ? "정예 몬스터 출현!" : "몬스터 출현!";

        if (content != null)
            content.SetActive(true);

        ActiveSequence = content != null ? content.GetComponent<UISpriteSequence>() : null;
        // The old 1.2 second timeout cut off the final three frames of the intro.
        yield return new WaitForSeconds(Mathf.Max(duration, ActiveSequence != null ? ActiveSequence.Duration : 0));

        HideAll();

        IsPlaying = false;

        onComplete?.Invoke();
    }

    private void HideAll()
    {
        ActiveSequence = null;
        if (fullscreen != null) fullscreen.SetActive(false);
        if (descendContent != null)
            descendContent.SetActive(false);

        if (battleIntroContent != null)
            battleIntroContent.SetActive(false);
    }
}
