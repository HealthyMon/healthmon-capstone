using System;
using System.Collections.Generic;
using UnityEngine;
using Healthmon.Common;

/// <summary>
/// Purchases without a server. Saves ownership, the chosen pet, and (only if the
/// existing PetStateManager can be written) the real LOCAL game coin balance.
/// Never changes server-owned coin or server pets.
/// </summary>
[DisallowMultipleComponent]
public sealed class HealthMonOfflineShopBackend : HealthMonShopBackend
{
    [Header("Catalog")]
    public HealthMonShopCatalog catalog;
    [Header("Standalone fallback wallet, used only when game coin is server-owned")]
    [Min(0)] public int initialOfflineCoins = 1200;
    public bool useWritablePetStateCoins = true;

    private const string WalletKey = "HealthMonShop_StandaloneCoins_v1";
    private const string OwnedKey = "HealthMonShop_OfflineOwned_v1";
    private const string SelectedKey = "HealthMonShop_OfflineSelectedPet_v1";
    private readonly HashSet<string> owned = new HashSet<string>();
    private bool loaded;

    [Serializable] private sealed class InventorySave { public List<string> ids = new List<string>(); }

    private void Awake() { Load(); }

    private void Load()
    {
        if (loaded) return;
        loaded = true;
        if (PlayerPrefs.HasKey(OwnedKey))
        {
            try
            {
                var data = JsonUtility.FromJson<InventorySave>(PlayerPrefs.GetString(OwnedKey));
                if (data != null && data.ids != null)
                    foreach (string id in data.ids) if (!string.IsNullOrEmpty(id)) owned.Add(id);
            }
            catch (Exception e) { Debug.LogWarning("[ShopOffline] 보유목록 읽기 실패: " + e.Message); }
        }
    }

    // A connected server means local purchases must be disabled. The server
    // purchase adapter should be installed separately when APIs become ready.
    public override bool IsReady => CommonServerConnection.Instance == null ||
                                      !CommonServerConnection.Instance.IsConnected;

    private PetStateManager WritableGameState
    {
        get
        {
            if (!useWritablePetStateCoins || CommonServerConnection.UsesServerAuthority) return null;
            return FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        }
    }

    public bool UsesGameCoin => WritableGameState != null;
    public int Balance => UsesGameCoin ? Mathf.Max(0, WritableGameState.CurrentCoin) :
        Mathf.Max(0, PlayerPrefs.GetInt(WalletKey, Mathf.Max(0, initialOfflineCoins)));

    public override bool IsOwned(string itemId)
    {
        Load();
        if (string.IsNullOrEmpty(itemId)) return false;
        foreach (var item in catalog != null ? catalog.items : new List<HealthMonShopItem>())
            if (item != null && item.itemId == itemId && item.includedByDefault) return true;
        return owned.Contains(itemId);
    }

    public override void Purchase(string itemId, Action<HealthMonShopPurchaseResult> callback)
    {
        if (!IsReady) { Fail(callback, "서버 연결 중에는 오프라인 구매를 사용할 수 없습니다."); return; }
        Load();
        HealthMonShopItem item = FindItem(itemId);
        if (item == null) { Fail(callback, "상품 목록에서 찾을 수 없습니다."); return; }
        if (IsOwned(itemId)) { Fail(callback, "이미 보유한 상품이에요."); return; }
        int price = Mathf.Max(0, item.displayCoinPrice);
        int money = Balance;
        if (money < price) { Fail(callback, "코인이 부족해요."); return; }

        int after = money - price;
        var state = WritableGameState;
        if (state != null)
        {
            // Uses existing local save/UI logic. This method refuses writes in
            // server-authority mode, which is why we only call it with writable state.
            state.SetAdminValues(state.CurrentLevel, after,
                state.CurrentIntimacy, state.CurrentActivity,
                state.CurrentKindness, state.CurrentCuriosity);
        }
        else PlayerPrefs.SetInt(WalletKey, after);

        owned.Add(itemId);
        PlayerPrefs.SetString(OwnedKey, JsonUtility.ToJson(new InventorySave { ids = new List<string>(owned) }));
        PlayerPrefs.Save();
        UnlockBaseJewelrySlot(item.jewelryName);
        callback?.Invoke(new HealthMonShopPurchaseResult { success = true,
            message = "오프라인 구매가 저장됐어요." });
    }

    public override void SelectCharacter(string itemId, Action<HealthMonShopPurchaseResult> callback)
    {
        if (!IsReady) { Fail(callback, "온라인 상태에서는 서버 선택 기능이 필요합니다."); return; }
        var item = FindItem(itemId);
        if (item == null || item.category != HealthMonShopCategory.Character || !IsOwned(itemId))
        { Fail(callback, "보유한 캐릭터만 선택할 수 있어요."); return; }
        PlayerPrefs.SetString(SelectedKey, itemId);
        PlayerPrefs.Save();
        callback?.Invoke(new HealthMonShopPurchaseResult { success = true,
            message = "캐릭터 선택을 저장했어요. 홈 외형 적용은 별도 연결이 필요합니다." });
    }

    public string SelectedCharacterId => PlayerPrefs.GetString(SelectedKey, "pet_starter");

    [ContextMenu("오프라인 테스트 코인 +1000")]
    public void AddTestCoins()
    {
        if (!IsReady) { Debug.LogWarning("[ShopOffline] 서버 연결 중이므로 중단했어요."); return; }
        int coin = Balance + 1000;
        var state = WritableGameState;
        if (state != null)
            state.SetAdminValues(state.CurrentLevel, coin, state.CurrentIntimacy, state.CurrentActivity,
                state.CurrentKindness, state.CurrentCuriosity);
        else { PlayerPrefs.SetInt(WalletKey, coin); PlayerPrefs.Save(); }
        Debug.Log("[ShopOffline] 테스트 코인 +1000. 현재=" + Balance);
    }

    private HealthMonShopItem FindItem(string itemId)
    {
        if (catalog == null || catalog.items == null) return null;
        foreach (var item in catalog.items)
            if (item != null && item.itemId == itemId) return item;
        return null;
    }

    private static void Fail(Action<HealthMonShopPurchaseResult> callback, string text)
    { callback?.Invoke(new HealthMonShopPurchaseResult { success = false, message = text }); }

    private static void UnlockBaseJewelrySlot(string name)
    {
        var c = FindFirstObjectByType<CustomizationPrototype>(FindObjectsInactive.Include);
        if (c == null) return;
        switch (name)
        {
            case "귀걸이": c.UnlockEarring(); break;
            case "펜던트": c.UnlockPendant(); break;
            case "반지": c.UnlockRing(); break;
        }
    }
}
