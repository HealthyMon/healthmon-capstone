using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using Healthmon.Common;

/// <summary>
/// Safe overlay on MainARScene/UI/Canvas. Does not touch UIManager, AR, pet preview or quests.
/// Reads the authoritative server coin balance; purchases only through a backend adapter.
/// </summary>
[DisallowMultipleComponent]
public sealed class HealthMonShopScreen : MonoBehaviour
{
    [Header("Catalog and server purchase adapter")]
    public HealthMonShopCatalog catalog;
    public HealthMonShopBackend backend;

    [Header("Overlay")]
    public GameObject overlay;
    public Button closeButton;
    public Button accessoriesTab;
    public Button charactersTab;
    [Header("Accessory filter buttons (optional)")]
    public Button filterAll;
    public Button filterNecklace;
    public Button filterEarring;
    public Button filterPendant;
    public Button filterRing;
    public TMP_Text filterStatus;
    [Header("Purchase success view")]
    public GameObject successPanel;
    public TMP_Text successTitle;
    public TMP_Text successDescription;
    public Image successIcon;
    public Button successCloseButton;
    public Sprite selectedTabSprite;
    public Sprite unselectedTabSprite;
    public TMP_Text currencyLabel;
    public TMP_Text hintLabel;

    [Header("Product list")]
    public RectTransform content;
    public ScrollRect scrollRect;
    public HealthMonShopProductCard cardTemplate;

    [Header("Selected item / checkout")]
    public TMP_Text selectedTitle;
    public TMP_Text selectedDescription;
    public TMP_Text selectedPrice;
    public Image selectedIcon;
    public Button actionButton;
    public TMP_Text actionText;
    public GameObject confirmPanel;
    public TMP_Text confirmText;
    public Button confirmButton;
    public Button cancelButton;

    private readonly List<HealthMonShopProductCard> cards = new List<HealthMonShopProductCard>();
    private HealthMonShopCategory currentCategory = HealthMonShopCategory.Accessory;
    private HealthMonShopItem selected;
    private bool busy;
    private string activeFilter = "";
    private float nextRefresh;
    private int previousCoin = int.MinValue;
    private bool previousConnected;

    private void Awake()
    {
        if (closeButton != null) closeButton.onClick.AddListener(CloseShop);
        if (accessoriesTab != null) accessoriesTab.onClick.AddListener(() => ChangeCategory(HealthMonShopCategory.Accessory));
        if (charactersTab != null) charactersTab.onClick.AddListener(() => ChangeCategory(HealthMonShopCategory.Character));
        if (actionButton != null) actionButton.onClick.AddListener(OnAction);
        WireFilter(filterAll, "");
        WireFilter(filterNecklace, "목걸이");
        WireFilter(filterEarring, "귀걸이");
        WireFilter(filterPendant, "펜던트");
        WireFilter(filterRing, "반지");
        if (successCloseButton != null) successCloseButton.onClick.AddListener(() => { if (successPanel != null) successPanel.SetActive(false); });
        if (confirmButton != null) confirmButton.onClick.AddListener(ConfirmPurchase);
        if (cancelButton != null) cancelButton.onClick.AddListener(() => { if (confirmPanel != null) confirmPanel.SetActive(false); });
        if (cardTemplate != null) cardTemplate.gameObject.SetActive(false);
        if (confirmPanel != null) confirmPanel.SetActive(false);
        if (successPanel != null) successPanel.SetActive(false);
        if (overlay != null) overlay.SetActive(false);
    }

    private void Update()
    {
        if (overlay == null || !overlay.activeSelf || Time.unscaledTime < nextRefresh) return;
        nextRefresh = Time.unscaledTime + 0.5f;
        int coins = CurrentCoin();
        bool connected = ServerConnected();
        if (coins != previousCoin || connected != previousConnected)
        {
            previousCoin = coins; previousConnected = connected;
            RefreshBalance();
        }
    }

    public void OpenShop()
    {
        if (overlay == null) { Debug.LogError("[HealthMonShop] Overlay not assigned.", this); return; }
        overlay.SetActive(true);
        selected = null;
        currentCategory = HealthMonShopCategory.Accessory;
        activeFilter = "";
        if (successPanel != null) successPanel.SetActive(false);
        if (confirmPanel != null) confirmPanel.SetActive(false);
        RefreshAll();
    }

    public void CloseShop()
    {
        if (busy) { ShowHint("구매 요청 처리 중에는 닫을 수 없습니다."); return; }
        if (overlay != null) overlay.SetActive(false);
    }

    private bool ServerConnected()
    {
        return CommonServerConnection.Instance != null && CommonServerConnection.Instance.IsConnected;
    }

    private int CurrentCoin()
    {
        // Offline-only purchases use a persistent local wallet. This never touches
        // authoritative server balances while the real server is connected.
        var local = backend as HealthMonOfflineShopBackend;
        if (local != null && local.IsReady) return local.Balance;
        if (CommonServerConnection.UsesServerAuthority)
        {
            var connection = CommonServerConnection.Instance;
            return connection != null && connection.IsConnected && connection.LatestState != null
                ? connection.LatestState.coin : -1;
        }
        var state = FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        return state == null ? -1 : state.CurrentCoin;
    }

    private void RefreshBalance()
    {
        if (currencyLabel != null)
        {
            int coin = CurrentCoin();
            currencyLabel.text = coin < 0 ? "코인 --" : coin.ToString("N0") + " C";
        }
        if (backend is HealthMonOfflineShopBackend localBackend && localBackend.IsReady)
            ShowHint(localBackend.UsesGameCoin ? "오프라인 상점 · 현재 게임 코인 사용" :
                "오프라인 상점 · 저장된 전용 코인 사용 (서버와 별도)");
        else if (CurrentCoin() < 0)
            ShowHint("서버에 연결하면 실제 코인 잔액을 불러옵니다.");
        else if (backend == null || !backend.IsReady)
            ShowHint("상점 UI 준비 완료 · 실제 구매는 서버 구매 API 연결 후 가능합니다.");
        else
            ShowHint("보유 코인으로 장신구와 새로운 헬스몬을 만나보세요.");
        RefreshActionButton();
    }

    private void ShowHint(string text)
    {
        if (hintLabel != null) hintLabel.text = text;
    }

    private bool IsOwned(HealthMonShopItem item)
    {
        if (item == null) return false;
        if (item.includedByDefault) return true;
        if (backend != null && backend.IsReady) return backend.IsOwned(item.itemId);
        // Existing locally unlocked jewelry may still be shown as owned in the UI.
        if (!string.IsNullOrEmpty(item.jewelryName))
        {
            var c = FindFirstObjectByType<CustomizationPrototype>(FindObjectsInactive.Include);
            return c != null && c.IsUnlocked(item.jewelryName);
        }
        return false;
    }

    private void ChangeCategory(HealthMonShopCategory category)
    {
        currentCategory = category;
        activeFilter = "";
        selected = null;
        RefreshAll();
    }

    private void WireFilter(Button button, string name)
    {
        if (button != null) button.onClick.AddListener(() => { activeFilter = name; selected = null; RefreshAll(); });
    }

    private bool InCurrentFilter(HealthMonShopItem item)
    {
        return item != null && item.category == currentCategory &&
            (currentCategory != HealthMonShopCategory.Accessory || string.IsNullOrEmpty(activeFilter) ||
             item.jewelryName == activeFilter);
    }

    private void RefreshAll()
    {
        RefreshTabs();
        RefreshBalance();
        RebuildCards();
        HealthMonShopItem itemToSelect = null;
        if (InCurrentFilter(selected)) itemToSelect = selected;
        else if (catalog != null)
            foreach (var item in catalog.items)
                if (InCurrentFilter(item)) { itemToSelect = item; break; }
        if (itemToSelect != null) SelectItem(itemToSelect);
        if (itemToSelect == null) { selected = null; if (selectedTitle != null) selectedTitle.text = "상품을 선택하세요"; RefreshActionButton(); }
        if (scrollRect != null) scrollRect.verticalNormalizedPosition = 1f;
    }

    private void RefreshTabs()
    {
        if (accessoriesTab != null && accessoriesTab.targetGraphic is Image a)
            a.sprite = currentCategory == HealthMonShopCategory.Accessory ? selectedTabSprite : unselectedTabSprite;
        if (charactersTab != null && charactersTab.targetGraphic is Image b)
            b.sprite = currentCategory == HealthMonShopCategory.Character ? selectedTabSprite : unselectedTabSprite;
    }

    private void RebuildCards()
    {
        foreach (var card in cards) if (card != null) Destroy(card.gameObject);
        cards.Clear();
        if (catalog == null || content == null || cardTemplate == null) return;
        var filtered = new List<HealthMonShopItem>();
        foreach (var item in catalog.items)
            if (InCurrentFilter(item)) filtered.Add(item);
        if (filterStatus != null) filterStatus.text = currentCategory == HealthMonShopCategory.Character ? "새로운 헬스몬을 만나보세요" : (string.IsNullOrEmpty(activeFilter) ? "전체 장신구" : activeFilter + " 상품") + " · " + filtered.Count + "개";
        SetFilterVisibility(currentCategory == HealthMonShopCategory.Accessory);

        // Character cards occupy a full row, like the shop design reference.
        // Accessories remain in the existing two-column grid.
        bool characterList = currentCategory == HealthMonShopCategory.Character;
        float tileW = characterList ? 884f : 446f;
        float tileH = characterList ? 326f : 350f;
        const float rowGap = 20f;
        int columns = characterList ? 1 : 2;
        int rows = (filtered.Count + columns - 1) / columns;
        content.sizeDelta = new Vector2(0, Mathf.Max(1, rows) * (tileH + rowGap) + 32f);
        for (int i = 0; i < filtered.Count; i++)
        {
            var card = Instantiate(cardTemplate, content, false);
            card.name = "ShopCard_" + filtered[i].itemId;
            var rt = card.transform as RectTransform;
            rt.anchorMin = rt.anchorMax = new Vector2(.5f, 1f);
            rt.pivot = new Vector2(.5f, 1f);
            rt.sizeDelta = new Vector2(tileW, tileH);
            float x = characterList ? 0 : (i % 2 == 0 ? -232 : 232);
            rt.anchoredPosition = new Vector2(x, -(i / columns) * (tileH + rowGap) - 14f);
            if (characterList)
            {
                if (card.icon != null)
                {
                    RectTransform icon = card.icon.rectTransform;
                    icon.anchoredPosition = new Vector2(-305, -158);
                    icon.sizeDelta = new Vector2(205, 205);
                }
                if (card.nameLabel != null)
                {
                    RectTransform label = card.nameLabel.rectTransform;
                    label.anchoredPosition = new Vector2(114, -86);
                    label.sizeDelta = new Vector2(570, 57);
                    card.nameLabel.alignment = TextAlignmentOptions.Left;
                }
                if (card.subtitleLabel != null)
                {
                    RectTransform label = card.subtitleLabel.rectTransform;
                    label.anchoredPosition = new Vector2(114, -162);
                    label.sizeDelta = new Vector2(570, 45);
                    card.subtitleLabel.alignment = TextAlignmentOptions.Left;
                }
                if (card.priceLabel != null)
                {
                    RectTransform label = card.priceLabel.rectTransform;
                    label.anchoredPosition = new Vector2(120, -258);
                    label.sizeDelta = new Vector2(565, 49);
                    card.priceLabel.alignment = TextAlignmentOptions.Right;
                }
            }
            card.gameObject.SetActive(true);
            card.Bind(filtered[i], IsOwned(filtered[i]), SelectItem);
            cards.Add(card);
        }
    }

    private void SetFilterVisibility(bool show)
    {
        foreach (var button in new [] { filterAll, filterNecklace, filterEarring, filterPendant, filterRing })
            if (button != null) button.gameObject.SetActive(show);
    }

    private void SelectItem(HealthMonShopItem item)
    {
        selected = item;
        if (selectedTitle != null) selectedTitle.text = item.displayName;
        if (selectedDescription != null) selectedDescription.text = item.description;
        if (selectedPrice != null) selectedPrice.text = IsOwned(item) ? "보유 중" : (item.displayCoinPrice.ToString("N0") + " C");
        if (selectedIcon != null) { selectedIcon.sprite = item.icon; selectedIcon.enabled = item.icon != null; selectedIcon.preserveAspect = true; }
        RefreshActionButton();
    }

    private void RefreshActionButton()
    {
        if (actionButton == null) return;
        bool owned = IsOwned(selected);
        bool hasAdapter = backend != null && backend.IsReady;
        bool enough = selected != null && CurrentCoin() >= selected.displayCoinPrice;
        bool selectingCharacter = owned && selected != null && selected.category == HealthMonShopCategory.Character;
        if (actionText != null)
            actionText.text = selected == null ? "상품을 선택하세요" :
                selectingCharacter ? "캐릭터 선택" : owned ? "이미 보유 중" :
                !hasAdapter ? "구매 서버 연결 필요" : !enough ? "코인이 부족해요" : "구매하기";
        actionButton.interactable = !busy && selected != null && hasAdapter &&
            (selectingCharacter || (!owned && enough));
    }

    private void OnAction()
    {
        if (busy || selected == null || backend == null || !backend.IsReady) return;
        if (IsOwned(selected))
        {
            if (selected.category != HealthMonShopCategory.Character) return;
            busy = true; RefreshActionButton();
            backend.SelectCharacter(selected.itemId, result =>
            {
                if (this == null) return;
                busy = false;
                ShowHint(result != null ? result.message : "캐릭터 선택에 실패했어요.");
                if (result != null && result.success && !(backend is HealthMonOfflineShopBackend))
                    CommonServerConnection.Instance?.RefreshState();
                RefreshActionButton();
            });
            return;
        }
        if (CurrentCoin() < selected.displayCoinPrice) { ShowHint("코인이 부족해요."); return; }
        if (confirmText != null) confirmText.text = selected.displayName + "\n" +
            selected.displayCoinPrice.ToString("N0") + " 코인으로 구매할까요?\n구매가 완료되면 되돌릴 수 없습니다.";
        if (confirmPanel != null) confirmPanel.SetActive(true);
    }

#if UNITY_EDITOR
    [ContextMenu("디자인 미리보기: 구매 확인창 (결제 없음)")]
    public void PreviewPurchaseDialog()
    {
        if (overlay != null) overlay.SetActive(true);
        if (selected == null && catalog != null && catalog.items.Count > 1) selected = catalog.items[1];
        if (selected != null && confirmText != null)
            confirmText.text = selected.displayName + "\n" + selected.displayCoinPrice.ToString("N0") +
                " 코인으로 구매할까요?\n(디자인 미리보기 — 실제 결제 없음)";
        if (confirmPanel != null) confirmPanel.SetActive(true);
    }
#endif

#if UNITY_EDITOR
    [ContextMenu("디자인 미리보기: 구매 성공창 (결제 없음)")]
    public void PreviewSuccessDialog()
    {
        if (overlay != null) overlay.SetActive(true);
        if (selected == null && catalog != null && catalog.items.Count > 1) selected = catalog.items[1];
        if (successTitle != null) successTitle.text = "구매 완료! (화면 테스트)";
        if (successDescription != null) successDescription.text = selected != null ? selected.displayName + "을(를) 획득했어요!" : "획득 예시 화면";
        if (successIcon != null) { successIcon.sprite = selected != null ? selected.icon : null; successIcon.enabled = successIcon.sprite != null; }
        if (confirmPanel != null) confirmPanel.SetActive(false);
        if (successPanel != null) successPanel.SetActive(true);
    }
#endif

    private void ConfirmPurchase()
    {
        if (busy || selected == null || backend == null || !backend.IsReady) return;
        if (confirmPanel != null) confirmPanel.SetActive(false);
        busy = true; RefreshActionButton();
        string requestedId = selected.itemId;
        backend.Purchase(requestedId, result =>
        {
            if (this == null) return;
            busy = false;
            if (result != null && result.success)
            {
                ShowHint("구매가 완료됐어요! 보유 목록을 갱신합니다.");
                if (!(backend is HealthMonOfflineShopBackend))
                    CommonServerConnection.Instance?.RefreshState();
                // Server-confirmed acquisition may be projected into the existing local jewelry view.
                if (selected != null && selected.itemId == requestedId && !string.IsNullOrEmpty(selected.jewelryName))
                {
                    var customization = FindFirstObjectByType<CustomizationPrototype>(FindObjectsInactive.Include);
                    if (customization != null)
                    {
                        switch (selected.jewelryName)
                        {
                            case "귀걸이": customization.UnlockEarring(); break;
                            case "펜던트": customization.UnlockPendant(); break;
                            case "반지": customization.UnlockRing(); break;
                        }
                    }
                }
            }
            else ShowHint(result != null ? result.message : "구매에 실패했어요.");
            RefreshAll();
            if (result != null && result.success)
            {
                ShowHint(backend is HealthMonOfflineShopBackend ?
                    "오프라인 구매 완료 · 보유 정보가 기기에 저장됐어요." :
                    "서버가 구매를 승인했습니다. 코인과 보유 목록을 확인하세요.");
                if (successTitle != null) successTitle.text = "구매 완료!";
                if (successDescription != null) successDescription.text = selected != null && selected.itemId == requestedId
                    ? selected.displayName + "을(를) 획득했어요!" : "새 상품을 획득했어요!";
                if (successIcon != null) { successIcon.sprite = selected != null ? selected.icon : null; successIcon.enabled = successIcon.sprite != null; }
                if (successPanel != null) successPanel.SetActive(true);
            }
        });
    }
}
