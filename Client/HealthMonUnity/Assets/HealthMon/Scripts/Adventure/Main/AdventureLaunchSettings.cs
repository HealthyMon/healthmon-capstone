/// <summary>메인 → 로딩 → 탐험 씬을 통과하는 일회성 진입 요청.</summary>
public static class AdventureLaunchSettings
{
    public enum Difficulty { Easy, Normal, Hard }
    public enum Region { Entrance, Checkpoint }

    public static Difficulty SelectedDifficulty { get; private set; } = Difficulty.Normal;
    public static Region SelectedRegion { get; private set; } = Region.Entrance;
    public static bool HasPendingLaunch { get; private set; }

    public static void Prepare(Difficulty difficulty, Region region)
    {
        SelectedDifficulty = difficulty;
        SelectedRegion = region;
        HasPendingLaunch = true;
    }

    public static bool ConsumeLaunch()
    {
        if (!HasPendingLaunch) return false;
        HasPendingLaunch = false;
        return true;
    }
}
