using System;
using UnityEngine;

[Serializable]
public class HealthMonShopPurchaseResult
{
    public bool success;
    public string message;
    public string newPetId;
}

/// <summary>
/// Connect this to your server team's authoritative shop endpoints.
/// IMPORTANT: The client never deducts server coins itself or assumes a purchase succeeded.
/// Server must validate ownership, price, currency, and unique transaction id atomically.
/// </summary>
public abstract class HealthMonShopBackend : MonoBehaviour
{
    public abstract bool IsReady { get; }
    public abstract bool IsOwned(string itemId);
    public abstract void Purchase(string itemId, Action<HealthMonShopPurchaseResult> callback);
    public virtual void SelectCharacter(string itemId, Action<HealthMonShopPurchaseResult> callback)
    {
        callback?.Invoke(new HealthMonShopPurchaseResult { success = false,
            message = "캐릭터 전환 API가 연결되지 않았습니다." });
    }
}
