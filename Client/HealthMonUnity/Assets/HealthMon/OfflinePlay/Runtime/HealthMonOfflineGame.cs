using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using Healthmon.Common;

/// <summary>
/// Real, persisted single-device offline growth. Uses the project's PetStateManager
/// and QuestPrototype instead of parallel fake stats/quests. Does not contact a server.
/// Food, walking and conversation are MANUAL / scripted offline gameplay, not AI or sensors.
/// </summary>
[DefaultExecutionOrder(800)]
public sealed class HealthMonOfflineGame : MonoBehaviour
{
    public const string ModeKey = "HealthMon_Offline_Mode_v1";
    private const string ActionKey = "HealthMon_Offline_Actions_v1";
    private const string WalkRecordsKey = "HealthMon_Offline_WorkoutRecords_v1";
    private const string WelcomeKey = "HealthMon_Offline_StarterGranted_v1";
    private const string QuestKey = "HealthMon_Quest_Save_v1";
    private const string GrowthMilestoneKey = "HealthMon_Offline_GrowthStage_v1";

    [Header("Existing game controllers")]
    public PetStateManager pet;
    public QuestPrototype quests;
    public DialoguePrototype serverDialogue;

    [Header("Existing panels")]
    public GameObject homePanel, foodPanel, dialoguePanel, questPanel, wearablePanel;

    [Header("Offline UI (installed by editor)")]
    public GameObject questSurface, foodSurface, dialogueSurface, workoutSurface, homeCareButton;
    public TMP_Text modeStatus, homeHint, foodNotice, dialogueLog, dialogueReply, workoutNotice;
    public TMP_Text questSummary, workoutSummary, workoutHistory, growthSummary;
    public TMP_InputField dialogueInput;
    public TMP_InputField stepInput;
    public OfflineQuestCard[] questCards;
    public Image[] weekBars;

    [Header("Starter allowance (once per install profile)")]
    [Min(0)] public int starterCoins = 200;

    [Serializable] public sealed class OfflineQuestCard
    {
        public TMP_Text progress;
        public TMP_Text claimLabel;
        public Image progressFill;
        public Button claimButton;
    }

    [Serializable] private sealed class DailyActions
    {
        public string date;
        public int steps;
        public int chats;
        public int interactions;
        public bool breakfast;
        public bool lunch;
        public bool dinner;
        public int walkExp;
    }
    [Serializable] private sealed class WalkingRecord
    {
        public string date;
        public string time;
        public int steps;
    }
    [Serializable] private sealed class WalkingHistory
    {
        public List<WalkingRecord> items = new List<WalkingRecord>();
    }
    [Serializable] private sealed class QuestSave
    {
        public string date;
        public int walkProgress, foodProgress, dialogueProgress, arProgress;
        public bool walkClaimed, foodClaimed, dialogueClaimed, arClaimed;
    }

    private DailyActions today;
    private WalkingHistory walking;
    private float nextRefresh;
    private bool activeOffline;

    public static bool Enabled => CommonServerConnection.LocalDemoEnabled;

    private void Start()
    {
        activeOffline = Enabled;
        foreach (var go in new[] { questSurface, foodSurface, dialogueSurface, workoutSurface, homeCareButton })
            if (go != null) go.SetActive(activeOffline);
        if (!activeOffline) return;
        if (pet == null) pet = FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        if (quests == null) quests = FindFirstObjectByType<QuestPrototype>(FindObjectsInactive.Include);
        if (serverDialogue == null) serverDialogue = FindFirstObjectByType<DialoguePrototype>(FindObjectsInactive.Include);

        LoadDaily(); LoadWalkHistory();
        // Replace old 1,200 synthetic starting steps with only user-entered offline steps.
        quests?.SetDailyWalkSteps(today.steps);
        // Unlike a cosmetic mockup, this grants a one-time starting balance in the REAL local PetState save.
        if (pet != null && !PlayerPrefs.HasKey(WelcomeKey))
        {
            if (starterCoins > 0) pet.AddReward(0, starterCoins);
            PlayerPrefs.SetInt(WelcomeKey, 1); PlayerPrefs.Save();
        }
        // The server-only chat script would disable the send button when no API is connected.
        // Keep the actual 3D AR character and show a separate offline conversation surface.
        if (serverDialogue != null) serverDialogue.enabled = false;
        if (dialoguePanel != null)
        {
            foreach (var text in dialoguePanel.GetComponentsInChildren<TMP_Text>(true))
                if (text != null && text.text.Contains("LLM 서버에 Connect")) text.text = "오프라인 교감 중";
        }
        if (modeStatus != null) modeStatus.text = "OFFLINE · 기기에 저장됨";
        if (dialogueReply != null) dialogueReply.text = "안녕! 오늘도 함께 건강한 습관을 만들어 볼까?";
        if (homeHint != null) homeHint.text = "오프라인 육성 중 · 쓰다듬기로 친밀도 UP";
        Refresh();
    }

    private void Update()
    {
        if (!activeOffline || Time.unscaledTime < nextRefresh) return;
        nextRefresh = Time.unscaledTime + .35f;
        if (today == null || today.date != DateTime.Now.ToString("yyyy-MM-dd")) LoadDaily();
        Refresh();
    }

    private static string Today => DateTime.Now.ToString("yyyy-MM-dd");
    private void LoadDaily()
    {
        try { today = JsonUtility.FromJson<DailyActions>(PlayerPrefs.GetString(ActionKey, "")); }
        catch { today = null; }
        if (today == null || today.date != Today) today = new DailyActions { date = Today };
        SaveDaily();
    }
    private void SaveDaily()
    {
        PlayerPrefs.SetString(ActionKey, JsonUtility.ToJson(today)); PlayerPrefs.Save();
    }
    private void LoadWalkHistory()
    {
        try { walking = JsonUtility.FromJson<WalkingHistory>(PlayerPrefs.GetString(WalkRecordsKey, "")); }
        catch { walking = null; }
        if (walking == null || walking.items == null) walking = new WalkingHistory();
    }
    private void SaveWalkHistory()
    {
        if (walking.items.Count > 100) walking.items.RemoveRange(0, walking.items.Count - 100);
        PlayerPrefs.SetString(WalkRecordsKey, JsonUtility.ToJson(walking)); PlayerPrefs.Save();
    }

    // Called by optional home button (real stats + quest progress, capped each day).
    public void PetCare()
    {
        if (!activeOffline || pet == null) return;
        if (today.interactions >= 15) { Notice("오늘 교감은 충분히 했어요. 내일 또 만나요!"); return; }
        today.interactions++;
        pet.AddIntimacy(2);
        pet.AddKindness(1);
        pet.AddExp(3);
        quests?.AddARInteraction();
        SaveDaily();
        Notice("헬스몬이 기뻐해요! 친밀도 +2 / 다정함 +1 / EXP +3");
        Refresh();
    }

    // Manual meal logging, NOT image recognition or verified calorie measurement.
    public void RecordBreakfast() { RecordMeal("아침"); }
    public void RecordLunch() { RecordMeal("점심"); }
    public void RecordDinner() { RecordMeal("저녁"); }
    private void RecordMeal(string type)
    {
        if (!activeOffline || pet == null) return;
        bool exists = type == "아침" ? today.breakfast : type == "점심" ? today.lunch : today.dinner;
        if (exists) { SetFoodNotice(type + " 식사는 오늘 이미 기록했어요."); return; }
        if (type == "아침") today.breakfast = true;
        else if (type == "점심") today.lunch = true;
        else today.dinner = true;
        quests?.AddFoodRecord();
        pet.AddReward(12, 4);
        pet.AddKindness(1);
        SaveDaily();
        SetFoodNotice(type + " 식사 수동 기록 완료! EXP +12 · 코인 +4\n실제 영양 분석이나 AI 판정은 포함하지 않아요.");
        Refresh();
    }

    public void SendOfflineMessage()
    {
        if (!activeOffline || pet == null || dialogueInput == null) return;
        string message = dialogueInput.text.Trim();
        if (message.Length == 0) return;
        if (message.Length > 160) message = message.Substring(0, 160);
        if (today.chats >= 20) { if (dialogueReply != null) dialogueReply.text = "오늘은 충분히 이야기했어. 내일 또 얘기하자!"; return; }
        today.chats++;
        quests?.AddDialogue();
        pet.AddIntimacy(2); pet.AddCuriosity(1); pet.AddExp(5);
        string reply = MakeOfflineReply(message);
        if (dialogueLog != null) dialogueLog.text = "나: " + message;
        if (dialogueReply != null) dialogueReply.text = reply;
        dialogueInput.text = "";
        SaveDaily(); Refresh();
    }
    private static string MakeOfflineReply(string msg)
    {
        if (msg.Contains("운동") || msg.Contains("걷")) return "멋져! 조금씩 걷는 습관을 함께 만들자!";
        if (msg.Contains("밥") || msg.Contains("음식") || msg.Contains("식사")) return "잘 챙겨 먹었구나! 식사 기록도 잊지 마!";
        if (msg.Contains("힘들") || msg.Contains("피곤")) return "오늘은 쉬어도 괜찮아. 충분한 휴식도 중요해!";
        if (msg.Contains("안녕") || msg.Contains("하이")) return "안녕! 오늘도 만나서 반가워!";
        if (msg.Contains("사랑") || msg.Contains("고마워")) return "나도 정말 기뻐! 우리 오래오래 함께하자.";
        return "그렇구나! 네 이야기를 들으니 즐거워. 우리 함께 성장하자!";
    }

    public void RecordSteps()
    {
        if (!activeOffline || pet == null) return;
        int steps;
        if (stepInput == null || !int.TryParse(stepInput.text, out steps) || steps < 1 || steps > 30000)
        { SetWorkoutNotice("1~30,000 사이의 걸음 수를 입력해 주세요."); return; }
        // Manual log is intentionally labelled as user-entered, not sensor-verified.
        today.steps = Mathf.Min(999999, today.steps + steps);
        quests?.SetDailyWalkSteps(today.steps);
        walking.items.Add(new WalkingRecord { date = Today, time = DateTime.Now.ToString("HH:mm"), steps = steps });
        int exp = Mathf.Min(Mathf.Max(0, 60 - today.walkExp), Mathf.Max(1, steps / 100));
        today.walkExp += exp;
        if (exp > 0) pet.AddExp(exp);
        pet.AddActivity(Mathf.Clamp(steps / 500, 1, 8));
        SaveDaily(); SaveWalkHistory();
        stepInput.text = "";
        SetWorkoutNotice("걸음 " + steps.ToString("N0") + "보를 수동으로 기록했어요. EXP +" + exp + " (일일 한도 60)");
        Refresh();
    }

    public void ClaimWalk() { ClaimQuest(0); }
    public void ClaimFood() { ClaimQuest(1); }
    public void ClaimDialogue() { ClaimQuest(2); }
    public void ClaimAR() { ClaimQuest(3); }

    public void ClaimQuest(int index)
    {
        if (!activeOffline || quests == null) return;
        switch (index)
        {
            case 0: quests.ClaimWalkReward(); break;
            case 1: quests.ClaimFoodReward(); break;
            case 2: quests.ClaimDialogueReward(); break;
            case 3: quests.ClaimARReward(); break;
        }
        Refresh();
    }

    private QuestSave ReadQuest()
    {
        try
        {
            var dto = JsonUtility.FromJson<QuestSave>(PlayerPrefs.GetString(QuestKey, ""));
            if (dto != null && dto.date == Today) return dto;
        }
        catch { }
        return new QuestSave { date = Today };
    }
    private void Refresh()
    {
        if (pet == null || today == null) return;
        // Growing up offline advances the saved growth stage, but does not invent an AI-made 3D model.
        int targetStage = pet.CurrentLevel >= 50 ? 3 : pet.CurrentLevel >= 30 ? 2 : pet.CurrentLevel >= 15 ? 1 : 0;
        if (targetStage > PlayerPrefs.GetInt(GrowthMilestoneKey, 0))
        {
            pet.ApplyEvolutionStage(targetStage);
            PlayerPrefs.SetInt(GrowthMilestoneKey, targetStage); PlayerPrefs.Save();
            Notice("성장 단계가 올랐어요! 3D 진화 외형은 서버 모델이 준비되면 적용해요.");
        }
        var q = ReadQuest();
        int[] values = { q.walkProgress, q.foodProgress, q.dialogueProgress, q.arProgress };
        int[] goals = { 3000, 1, 1, 3 };
        bool[] claimed = { q.walkClaimed, q.foodClaimed, q.dialogueClaimed, q.arClaimed };
        int done = 0;
        if (questCards != null)
        for (int i = 0; i < questCards.Length && i < 4; i++)
        {
            var card = questCards[i]; if (card == null) continue;
            int current = Mathf.Clamp(values[i], 0, goals[i]);
            bool ready = current >= goals[i]; if (ready) done++;
            if (card.progress != null) card.progress.text = current.ToString("N0") + " / " + goals[i].ToString("N0");
            if (card.progressFill != null) card.progressFill.fillAmount = (float)current / goals[i];
            if (card.claimLabel != null) card.claimLabel.text = claimed[i] ? "수령 완료" : ready ? "보상 받기" : "진행 중";
            if (card.claimButton != null) card.claimButton.interactable = ready && !claimed[i];
        }
        if (questSummary != null) questSummary.text = "오늘의 목표  " + done + " / 4";
        if (growthSummary != null) growthSummary.text = "Lv." + pet.CurrentLevel + "   코인 " + pet.CurrentCoin.ToString("N0") +
            "   친밀도 " + pet.CurrentIntimacy + "   활동성 " + pet.CurrentActivity +
            "\n다정함 " + pet.CurrentKindness + "   호기심 " + pet.CurrentCuriosity;
        if (workoutSummary != null) workoutSummary.text = "오늘 수동 기록  " + today.steps.ToString("N0") + "보  ·  기록 " + walking.items.Count + "회";
        if (workoutHistory != null)
        {
            string lines = "최근 걸음 기록\n";
            for (int i = walking.items.Count - 1, n = 0; i >= 0 && n < 4; i--, n++)
            { var r = walking.items[i]; lines += r.date.Substring(5) + " " + r.time + "   +" + r.steps.ToString("N0") + "보\n"; }
            workoutHistory.text = lines;
        }
        if (weekBars != null)
        {
            for (int i = 0; i < weekBars.Length; i++)
            {
                var date = DateTime.Now.Date.AddDays(i - weekBars.Length + 1).ToString("yyyy-MM-dd");
                int sum = 0;
                foreach (var record in walking.items) if (record.date == date) sum += record.steps;
                if (weekBars[i] != null) weekBars[i].fillAmount = Mathf.Clamp01((float)sum / 6000f);
            }
        }
    }

    private void Notice(string text) { if (homeHint != null) homeHint.text = text; }
    private void SetFoodNotice(string text) { if (foodNotice != null) foodNotice.text = text; }
    private void SetWorkoutNotice(string text) { if (workoutNotice != null) workoutNotice.text = text; }

    private void OnApplicationPause(bool pause) { if (pause && activeOffline) { SaveDaily(); SaveWalkHistory(); pet?.SavePetData(); } }
    private void OnApplicationQuit() { if (activeOffline) { SaveDaily(); SaveWalkHistory(); pet?.SavePetData(); } }
}
