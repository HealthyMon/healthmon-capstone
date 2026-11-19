using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using Healthmon.Beta;
using Healthmon.Common;
using UnityEngine;

/// <summary>Projects verified server inventory; never writes a local wallet.</summary>
[DisallowMultipleComponent]
public sealed class HealthMonServerShopBackend : HealthMonShopBackend
{
    public HealthMonShopCatalog catalog;
    public event Action Changed;
    public string Status { get; private set; } = "상점 정보를 불러오는 중이에요.";
    public string SelectedCharacterId => IsReady ? snapshot.selected_character_id : "";
    private ShopSnapshot snapshot;
    private string scope;
    private float nextRefresh;
    private bool loading;
    private readonly Dictionary<string, ShopItem> products = new Dictionary<string, ShopItem>();
    private readonly HashSet<string> owned = new HashSet<string>();
    [Serializable] private class Pending { public string requestId, itemId, operation; public int price; }
    private CommonServerConnection Connection => CommonServerConnection.Instance;
    private string CurrentScope
    {
        get
        {
            var c = Connection;
            return !CommonServerConnection.UsesServerAuthority || c == null || !c.IsConnected || c.Api == null ? null :
                c.Api.BaseUrl + "\n" + c.ServerInstanceId + "\n" + c.OwnerId + "\n" + c.Api.PetId;
        }
    }
    public override bool IsReady => snapshot != null && CurrentScope != null && scope == CurrentScope;
    public override bool IsOwned(string itemId) => IsReady && owned.Contains(itemId);
    public bool IsAvailable(string itemId) => IsReady && products.ContainsKey(itemId);
    public bool IsSelected(string itemId) => IsReady && snapshot.selected_character_id == itemId;

    private void Update()
    {
        string current = CurrentScope;
        if (scope != current)
        {
            scope = current; snapshot = null; products.Clear(); owned.Clear(); loading = false; nextRefresh = 0;
            FindFirstObjectByType<CustomizationPrototype>(FindObjectsInactive.Include)?.ApplyServerShopInventory(null);
            Status = current == null ? "서버에 연결하면 상점을 이용할 수 있어요." : "상점 정보를 불러오는 중이에요.";
            Changed?.Invoke();
        }
        if (current != null && snapshot == null && Time.unscaledTime >= nextRefresh && !loading && !Connection.Api.IsShopBusy)
            Refresh();
    }
    public void Refresh()
    {
        string requestedScope = CurrentScope;
        if (requestedScope == null || loading || Connection.Api.IsShopBusy) return;
        scope = requestedScope; loading = true; nextRefresh = Time.unscaledTime + 10;
        Connection.Api.GetShop(result =>
        {
            loading = false;
            if (CurrentScope != requestedScope) return;
            Apply(result);
            // A response may have been lost after commit. Reconcile on reconnect
            // before offering another purchase; no credential is persisted here.
            var pending = ReadPending(requestedScope);
            if (pending != null && ((pending.operation == "purchase" && owned.Contains(pending.itemId)) ||
                (pending.operation == "select" && result.selected_character_id == pending.itemId))) ClearPending(requestedScope);
            Status = "서버 코인 · 구매와 보유 정보가 자동 저장됩니다.";
            Changed?.Invoke();
        }, error =>
        {
            loading = false;
            if (CurrentScope != requestedScope) return;
            snapshot = null; Status = ErrorMessage(error); Changed?.Invoke();
        });
    }
    private void Apply(ShopSnapshot result)
    {
        snapshot = result; products.Clear(); owned.Clear();
        foreach (var product in result.items) products[product.item_id] = product;
        foreach (var id in result.owned_item_ids) owned.Add(id);
        if (catalog != null)
            foreach (var item in catalog.items)
                if (products.TryGetValue(item.itemId, out var product))
                { item.displayCoinPrice = product.coin_price; item.includedByDefault = product.included_by_default; }
        var slots = new List<string>();
        if (catalog != null) foreach (var item in catalog.items)
            if (owned.Contains(item.itemId) && !string.IsNullOrEmpty(item.jewelryName)) slots.Add(item.jewelryName);
        FindFirstObjectByType<CustomizationPrototype>(FindObjectsInactive.Include)?.ApplyServerShopInventory(slots);
    }
    public override void Purchase(string itemId, Action<HealthMonShopPurchaseResult> callback)
    { Mutate(itemId, "purchase", callback); }
    public override void SelectCharacter(string itemId, Action<HealthMonShopPurchaseResult> callback)
    { Mutate(itemId, "select", callback); }
    private void Mutate(string itemId, string operation, Action<HealthMonShopPurchaseResult> callback)
    {
        if (!IsReady || !products.TryGetValue(itemId, out var product))
        { Complete(callback, false, "상점 정보를 먼저 불러와 주세요."); return; }
        if (Connection.Api.IsShopBusy)
        { Complete(callback, false, "상점 정보를 갱신 중이에요. 잠시 후 다시 눌러 주세요."); return; }
        string requestedScope = scope;
        var pending = ReadPending(requestedScope);
        if (pending != null && (pending.itemId != itemId || pending.operation != operation))
        { Complete(callback, false, "이전 상품의 요청 결과를 확인 중이에요. 해당 상품을 다시 시도해 주세요."); Refresh(); return; }
        pending = pending ?? new Pending { requestId = Guid.NewGuid().ToString("N"), itemId = itemId,
            operation = operation, price = product.coin_price };
        PlayerPrefs.SetString(PendingKey(requestedScope), JsonUtility.ToJson(pending)); PlayerPrefs.Save();
        Action<ShopSnapshot> succeeded = result =>
        {
            if (this == null) return;
            if (CurrentScope != requestedScope) { Complete(callback, false, "연결이 변경됐어요. 다시 상점을 열어 주세요."); return; }
            if (!result.success) { Complete(callback, false, "서버 구매 결과를 확인할 수 없어요. 다시 시도해 주세요."); return; }
            Apply(result); ClearPending(requestedScope);
            Status = operation == "purchase" ? (result.already_owned ? "이미 보유한 상품이에요. 추가 코인은 차감하지 않았어요." : "구매가 서버에 저장됐어요.") :
                "캐릭터 선택을 서버에 저장했어요. 외형은 모델 교체 작업에서 적용합니다.";
            Changed?.Invoke(); Complete(callback, true, Status);
        };
        Action<ApiFailure> failed = error =>
        {
            if (this == null) return;
            // Transport/server errors can hide a committed transaction; preserve
            // its exact ID and price across retries and application restarts.
            if (error.StatusCode >= 400 && error.StatusCode < 500 && error.StatusCode != 401 && error.StatusCode != 408 && error.StatusCode != 429)
                ClearPending(requestedScope);
            Status = ErrorMessage(error); Complete(callback, false, Status);
            if (CurrentScope == requestedScope && error.StatusCode == 409) Refresh();
        };
        if (operation == "purchase") Connection.Api.PurchaseShopItem(new ShopPurchaseRequest {
            request_id = pending.requestId, item_id = itemId, expected_price = pending.price }, succeeded, failed);
        else Connection.Api.SelectShopCharacter(new ShopSelectionRequest { request_id = pending.requestId, item_id = itemId }, succeeded, failed);
    }
    private static void Complete(Action<HealthMonShopPurchaseResult> callback, bool ok, string message)
    { callback?.Invoke(new HealthMonShopPurchaseResult { success = ok, message = message }); }
    private static string PendingKey(string value)
    {
        using (var hash = SHA256.Create())
            return "HealthMonShop_Pending_v1_" + BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-", "");
    }
    private static Pending ReadPending(string value)
    {
        try { return JsonUtility.FromJson<Pending>(PlayerPrefs.GetString(PendingKey(value), "")); }
        catch (Exception) { return null; }
    }
    private static void ClearPending(string value) { PlayerPrefs.DeleteKey(PendingKey(value)); PlayerPrefs.Save(); }
    private static string ErrorMessage(ApiFailure error)
    {
        switch (error.Code)
        {
            case "shop_insufficient_coin": return "코인이 부족해요. 현재 잔액을 다시 확인해 주세요.";
            case "shop_price_changed": return "상품 가격이 변경됐어요. 상점을 다시 열고 확인해 주세요.";
            case "shop_not_owned": return "보유한 캐릭터만 선택할 수 있어요.";
            case "shop_item_not_found": return "현재 판매하지 않는 상품이에요.";
            case "shop_request_conflict": return "요청 정보가 달라요. 상점을 다시 열고 시도해 주세요.";
        }
        return error.StatusCode == 401 || error.StatusCode == 403 ? "서버 연결과 계정을 확인해 주세요." :
            "서버 응답을 확인하지 못했어요. 재시도해도 중복 결제되지 않습니다.";
    }
}
