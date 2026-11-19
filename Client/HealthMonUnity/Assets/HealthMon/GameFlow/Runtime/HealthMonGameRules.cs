using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
using Healthmon.Common;

/// <summary>
/// Offline-only deterministic daily/weekly progression adjunct.
/// PetStateManager owns level/EXP/coin and character-roster owns the selected pet.
/// This class owns daily exercise settlement, 7-day personality reviews and initiative.
/// No backend calls or fake sensor values. Valid recorded exercise only.
/// </summary>
[DisallowMultipleComponent]
[DefaultExecutionOrder(1100)]
public sealed class HealthMonGameRules : MonoBehaviour
{
    public const string SaveKey = "HealthMon_GameFlow_Rules_v1";
    public const int WalkTarget = 6000, UpperTarget = 30, CardioTarget = 20;
    public static HealthMonGameRules Instance { get; private set; }

    [Serializable] public sealed class DayLog
    {
        public string date;
        public int steps, upperReps, cardioMinutes, care, chats, meals;
        public int upperExp, cardioExp;
        public bool settled;
    }
    [Serializable] public sealed class CharacterRules
    {
        public string id;
        public int lowerBody = 50, upperBody = 50, stamina = 50, initiative = 20;
        public int pendingActivity, pendingKindness, pendingCuriosity;
        public string nextReviewDate = "";
        public List<DayLog> days = new List<DayLog>();
    }
    [Serializable] private sealed class SaveRoot
    {
        public int version = 1;
        public List<CharacterRules> profiles = new List<CharacterRules>();
    }

    public PetStateManager pet;
    public HealthMonCharacterRosterController roster;
    public event Action Changed;
    private SaveRoot save = new SaveRoot();
    private float nextCheck;
    private string currentId = "";
    public bool IsOffline => !CommonServerConnection.UsesServerAuthority;
    public string CharacterId => currentId;

    private void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(this); return; }
        Instance = this;
        Read();
    }
    private IEnumerator Start()
    {
        // CharacterRoster and PetStateManager initialize after Unity Start.
        yield return null;
        Bind();
        yield return null;
        Bind();
        if (IsOffline) Tick(true);
    }
    private void OnDestroy() { if (Instance == this) Instance = null; }
    private void OnApplicationPause(bool pause) { if (pause && IsOffline) Write(); }
    private void OnApplicationQuit() { if (IsOffline) Write(); }
    private void Update()
    {
        if (!IsOffline || Time.unscaledTime < nextCheck) return;
        nextCheck = Time.unscaledTime + 0.7f;
        Tick(false);
    }
    private void Bind()
    {
        if (pet == null) pet = FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        if (roster == null) roster = FindFirstObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
    }
    private string SelectedId()
    {
        if (roster != null && !string.IsNullOrEmpty(roster.CurrentCharacterId)) return roster.CurrentCharacterId;
        return PlayerPrefs.GetString("HealthMon_Roster_Selected_v1", "pet_starter");
    }
    private void Tick(bool force)
    {
        Bind();
        string id = SelectedId();
        if (id != currentId || force)
        {
            currentId = id;
            // Roster loads a new character during the same frame; let its StateManager settle.
            ApplyPending(Current());
            Changed?.Invoke();
        }
        var c = Current();
        bool changed = SettlePastDays(c);
        changed |= ReviewEligibleWeeks(c);
        if (changed) { Write(); Changed?.Invoke(); }
    }
    private CharacterRules Current()
    {
        if (string.IsNullOrEmpty(currentId)) currentId = SelectedId();
        return ForId(currentId);
    }
    public CharacterRules ForId(string id)
    {
        if (save.profiles == null) save.profiles = new List<CharacterRules>();
        foreach (var p in save.profiles) if (p != null && p.id == id) return p;
        var added = new CharacterRules { id = id };
        save.profiles.Add(added);
        Write();
        return added;
    }
    private static string Today => DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    private static bool Parse(string value, out DateTime date) => DateTime.TryParseExact(
        value, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out date);
    private DayLog TodayLog(CharacterRules p)
    {
        foreach (var log in p.days) if (log != null && log.date == Today) return log;
        var created = new DayLog { date = Today };
        p.days.Add(created);
        if (string.IsNullOrEmpty(p.nextReviewDate))
            p.nextReviewDate = DateTime.Today.AddDays(7).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        return created;
    }
    private static int Delta(float completionPercent)
    {
        if (completionPercent < 40f) return -2;
        if (completionPercent < 70f) return -1;
        if (completionPercent < 100f) return 1;
        if (completionPercent < 120f) return 2;
        return 3;
    }
    public static int CalculateDailyDelta(int actual, int target)
    {
        // No verified/manual record => no penalty, even if target not met.
        if (actual <= 0 || target <= 0) return 0;
        return Delta(100f * actual / target);
    }
    private bool SettlePastDays(CharacterRules c)
    {
        bool modified = false;
        foreach (var d in c.days)
        {
            if (d == null || d.settled || !Parse(d.date, out var day) || day.Date >= DateTime.Today) continue;
            c.lowerBody = Mathf.Clamp(c.lowerBody + CalculateDailyDelta(d.steps, WalkTarget), 0, 100);
            c.upperBody = Mathf.Clamp(c.upperBody + CalculateDailyDelta(d.upperReps, UpperTarget), 0, 100);
            c.stamina = Mathf.Clamp(c.stamina + CalculateDailyDelta(d.cardioMinutes, CardioTarget), 0, 100);
            d.settled = true;
            modified = true;
        }
        // Keep logs long enough for seven-day reviews, plus a safety margin.
        if (c.days.Count > 120)
        {
            c.days.RemoveAll(d => d == null || !Parse(d.date, out var dt) || dt.Date < DateTime.Today.AddDays(-120));
            modified = true;
        }
        return modified;
    }
    private static int PersonalityBonus(int days, float average)
    {
        if (days >= 5 && average >= 90) return 3;
        if (days >= 4 && average >= 70) return 2;
        if (days >= 2 && average >= 50) return 1;
        return 0;
    }
    private bool ReviewEligibleWeeks(CharacterRules c)
    {
        if (!Parse(c.nextReviewDate, out var next)) return false;
        int periods = 0;
        while (next.Date <= DateTime.Today && periods < 26)
        {
            DateTime begin = next.Date.AddDays(-7);
            int activeDays = 0, contactDays = 0, curiousDays = 0;
            float totalPercent = 0f;
            foreach (var d in c.days)
            {
                if (d == null || !Parse(d.date, out var day) || day.Date < begin || day.Date >= next.Date) continue;
                if (d.steps > 0 || d.upperReps > 0 || d.cardioMinutes > 0)
                {
                    activeDays++;
                    totalPercent += Mathf.Min(150f, Mathf.Max(d.steps * 100f / WalkTarget,
                        d.upperReps * 100f / UpperTarget, d.cardioMinutes * 100f / CardioTarget));
                }
                if (d.care + d.chats >= 2) contactDays++;
                if (d.chats >= 1 && d.meals >= 1) curiousDays++;
            }
            float mean = activeDays == 0 ? 0 : totalPercent / activeDays;
            int activityBonus = PersonalityBonus(activeDays, mean);
            int careBonus = contactDays >= 5 ? 3 : contactDays >= 4 ? 2 : contactDays >= 2 ? 1 : 0;
            int curiosityBonus = curiousDays >= 5 ? 3 : curiousDays >= 4 ? 2 : curiousDays >= 2 ? 1 : 0;
            c.pendingActivity += activityBonus;
            c.pendingKindness += careBonus;
            c.pendingCuriosity += curiosityBonus;
            c.initiative = Mathf.Clamp(c.initiative + activityBonus, 0, 100);
            next = next.AddDays(7);
            periods++;
        }
        if (periods == 0) return false;
        c.nextReviewDate = next.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        ApplyPending(c);
        return true;
    }
    private void ApplyPending(CharacterRules c)
    {
        // Only mutate the currently active character's PetStateManager. Inactive profiles
        // accumulate deltas and receive them when the roster loads that character.
        if (pet == null || c == null || c.id != SelectedId() || !IsOffline) return;
        if (c.pendingActivity != 0) { pet.AddActivity(c.pendingActivity); c.pendingActivity = 0; }
        if (c.pendingKindness != 0) { pet.AddKindness(c.pendingKindness); c.pendingKindness = 0; }
        if (c.pendingCuriosity != 0) { pet.AddCuriosity(c.pendingCuriosity); c.pendingCuriosity = 0; }
        Write();
    }
    private void SaveAction(Action<DayLog> update)
    {
        if (!IsOffline) return;
        var c = Current();
        SettlePastDays(c); ReviewEligibleWeeks(c);
        update(TodayLog(c));
        Write(); Changed?.Invoke();
    }
    public void RecordCare() => SaveAction(d => d.care++);
    public void RecordChat(string message) => SaveAction(d => d.chats++);
    public void RecordMeal(string type) => SaveAction(d => d.meals++);
    public void RecordSteps(int additionalSteps)
    {
        if (additionalSteps <= 0) return;
        SaveAction(d => d.steps = Mathf.Min(999999, d.steps + additionalSteps));
    }
    public void RecordUpper(int repetitions)
    {
        if (!IsOffline || pet == null || repetitions < 1 || repetitions > 1000) return;
        var d = TodayLog(Current());
        d.upperReps = Mathf.Min(99999, d.upperReps + repetitions);
        int total = Mathf.Min(30, d.upperReps / 10 * 3);
        int earned = Mathf.Max(0, total - d.upperExp);
        d.upperExp += earned;
        if (earned > 0) pet.AddExp(earned);
        Write(); Changed?.Invoke();
    }
    public void RecordCardio(int minutes)
    {
        if (!IsOffline || pet == null || minutes < 1 || minutes > 300) return;
        var d = TodayLog(Current());
        d.cardioMinutes = Mathf.Min(99999, d.cardioMinutes + minutes);
        int total = Mathf.Min(40, d.cardioMinutes * 2);
        int earned = Mathf.Max(0, total - d.cardioExp);
        d.cardioExp += earned;
        if (earned > 0) pet.AddExp(earned);
        Write(); Changed?.Invoke();
    }
    public string PersonalityHint => Current().initiative >= 80
        ? "선택 가능한 활동을 먼저 제안" : "사용자가 활동을 선택하도록 안내";
    public int CurrentInitiative => Current().initiative;
    public string GetSummary()
    {
        var p = Current(); var d = TodayLog(p);
        return "캐릭터: " + p.id + "   Lv." + (pet != null ? pet.CurrentLevel : 1) +
               "   EXP/코인: 기존 게임 상태 사용\n" +
               "생활 스탯  하체 " + p.lowerBody + "  상체 " + p.upperBody + "  지구력 " + p.stamina +
               "\n성격 스탯  활동성 " + (pet != null ? pet.CurrentActivity : 0) + "  다정함 " +
               (pet != null ? pet.CurrentKindness : 0) + "  호기심 " +
               (pet != null ? pet.CurrentCuriosity : 0) + "  주도성 " + p.initiative +
               "\n오늘 기록  걸음 " + d.steps + "보 · 상체 " + d.upperReps + "회 · 유산소 " + d.cardioMinutes + "분" +
               "\n다음 성격 평가: " + (string.IsNullOrEmpty(p.nextReviewDate) ? "첫 기록 7일 후" : p.nextReviewDate) +
               "\n진화: " + EvolutionStatus() + "\n대화 지침: " + PersonalityHint;
    }
    private static int CompletedStage(string stage)
    {
        if (string.IsNullOrEmpty(stage)) return 0;
        return stage.Contains("3차") ? 3 : stage.Contains("2차") ? 2 : stage.Contains("1차") ? 1 : 0;
    }
    public int NextEligibleStage()
    {
        if (!IsOffline || pet == null) return 0;
        PetStateManager.PetSaveData data = null;
        try { data = JsonUtility.FromJson<PetStateManager.PetSaveData>(PlayerPrefs.GetString("HealthMon_Pet_Save_v1", "")); } catch {}
        if (data == null) return 0;
        int next = CompletedStage(data.growthStage) + 1;
        if (next > 3) return 0;
        int[] levels = { 1, 15, 30, 50 }, affinity = { 0, 40, 60, 80 }, active = { 0, 30, 50, 70 };
        return data.level >= levels[next] && data.intimacy >= affinity[next] && data.activity >= active[next] ? next : 0;
    }
    public string EvolutionStatus()
    {
        int readyStage = NextEligibleStage();
        if (readyStage > 0) return readyStage + "차 진화 가능 (모델 변경은 별도)";
        return "레벨·친밀도·활동성 조건을 확인하세요";
    }
    public void AdvanceOfflineStage()
    {
        int next = NextEligibleStage();
        if (!IsOffline || next == 0 || pet == null) return;
        pet.ApplyEvolutionStage(next);
        Write(); Changed?.Invoke();
    }
    private void Read()
    {
        try { save = JsonUtility.FromJson<SaveRoot>(PlayerPrefs.GetString(SaveKey, "")); }
        catch { save = null; }
        if (save == null || save.profiles == null) save = new SaveRoot();
    }
    private void Write()
    {
        if (!IsOffline || HealthMonGameReset.IsResetPending) return;
        PlayerPrefs.SetString(SaveKey, JsonUtility.ToJson(save)); PlayerPrefs.Save();
    }
}
