
using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;

public enum AdventureDialogueType
{
    Entrance,
    Descending,
    Battle,
    EliteBattle,
    Reward,
    Rest,
    Quiz,
    Special,
    Victory,
    Defeat,
    NoEvent
}

[Serializable]
public class AdventureDialogueData
{
    public AdventureDialogueType type;

    [TextArea(2, 4)]
    public List<string> lines = new List<string>();
}

public class AdventureDialogueManager : MonoBehaviour
{
    [Header("Dialogue UI")]
    [SerializeField] private TMP_Text eventDescription;

    [Header("Dialogue List")]
    [SerializeField]
    private List<AdventureDialogueData> dialogues = new()
    {
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Entrance,
            lines = new List<string>
            {
                "동굴의 입구에 도착했다. 탐험을 시작하자!"
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Descending,
            lines = new List<string>
            {
                "다음 층으로 이동 중...",
                "계단을 따라 아래층으로 내려가고 있다."
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Battle,
            lines = new List<string>
            {
                "적이 나타났다! 전투가 시작된다!",
                "어둠 속에서 몬스터가 모습을 드러냈다!"
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.EliteBattle,
            lines = new List<string>
            {
                "강력한 적의 기운이 느껴진다. 정예 전투가 시작된다!"
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Reward,
            lines = new List<string>
            {
                "보물상자를 발견했다. 열어보자!",
                "반짝이는 보물이 눈앞에 나타났다!"
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Rest,
            lines = new List<string>
            {
                "안전한 장소를 발견했다. 잠시 쉬어가자."
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Quiz,
            lines = new List<string>
            {
                "수수께끼가 적힌 비석을 발견했다."
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Special,
            lines = new List<string>
            {
                "이상한 기운이 느껴진다. 무슨 일이 일어날까?"
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Victory,
            lines = new List<string>
            {
                "전투에서 승리했다! 다음 층으로 진행할 수 있다."
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.Defeat,
            lines = new List<string>
            {
                "전투에서 패배했다. 탐험이 종료되었다."
            }
        },
        new AdventureDialogueData
        {
            type = AdventureDialogueType.NoEvent,
            lines = new List<string>
            {
                "주변은 조용하다. 다음 층으로 이동할 수 있다."
            }
        }
    };

    public string GetDialogue(AdventureDialogueType type)
    {
        AdventureDialogueData data =
            dialogues.Find(d => d != null && d.type == type);

        if (data == null || data.lines == null)
            return "";

        List<string> validLines = data.lines.FindAll(
            line => !string.IsNullOrWhiteSpace(line)
        );

        if (validLines.Count == 0)
            return "";

        int index = UnityEngine.Random.Range(0, validLines.Count);

        return validLines[index];
    }

    public void ShowDialogue(AdventureDialogueType type)
    {
        SetDialogue(GetDialogue(type));
    }

    public void SetDialogue(string text)
    {
        if (eventDescription != null)
            eventDescription.text = text ?? "";
    }
}
