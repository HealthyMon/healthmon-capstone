
using System;
using System.Collections;
using UnityEngine;

public class AdventureTransitionUI : MonoBehaviour
{
    [Header("Content")]
    [SerializeField] private GameObject descendContent;
    [SerializeField] private GameObject battleIntroContent;

    [Header("Status UI - Hide During Transitions")]
    [SerializeField] private GameObject adventurePlayerStatusPanel;

    [Header("Dialogue")]
    [SerializeField] private AdventureDialogueManager dialogueManager;

    [Header("Duration")]
    [SerializeField, Min(0.1f)]
    private float descendDuration = 1.8f;

    [SerializeField, Min(0.1f)]
    private float battleDuration = 1.2f;

    public bool IsPlaying { get; private set; }

    private void Awake()
    {
        HideAll();
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
                "[Adventure] �ٸ� ������ ��� ���Դϴ�."
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

        // Hide exploration status while a floor / battle introduction plays.
        bool wasStatusVisible = adventurePlayerStatusPanel != null
            && adventurePlayerStatusPanel.activeSelf;
        if (adventurePlayerStatusPanel != null)
            adventurePlayerStatusPanel.SetActive(false);

        HideAll();

        if (dialogueManager != null)
            dialogueManager.ShowDialogue(dialogue);

        if (content != null)
            content.SetActive(true);

        yield return new WaitForSeconds(duration);

        HideAll();

        IsPlaying = false;

        // Floor descent resumes exploration. A battle introduction hands
        // visibility over to BattleController.BeginBattle() instead.
        if (content == descendContent && wasStatusVisible
            && adventurePlayerStatusPanel != null)
            adventurePlayerStatusPanel.SetActive(true);

        onComplete?.Invoke();
    }

    private void HideAll()
    {
        if (descendContent != null)
            descendContent.SetActive(false);

        if (battleIntroContent != null)
            battleIntroContent.SetActive(false);
    }
}
