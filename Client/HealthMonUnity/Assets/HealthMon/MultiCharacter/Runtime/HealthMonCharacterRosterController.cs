using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using Healthmon.Common;

/// <summary>
/// One-scene character roster for OFFLINE progression, without touching the existing
/// PetStateManager/CustomizationPrototype source or UnityEvent connections.
/// Global coins and shared unlocks; per-character EXP, level, stats, outfit selections.
/// The existing AR pet and generated AI models are NOT replaced by this version.
/// Online mode is intentionally read-only until the pet-select API is integrated.
/// </summary>
[DisallowMultipleComponent]
[DefaultExecutionOrder(850)]
public sealed class HealthMonCharacterRosterController : MonoBehaviour
{
    private const string LegacyPet = "HealthMon_Pet_Save_v1";
    private const string LegacyJewelry = "HealthMon_Customization_Jewelry_v3";
    private const string LegacyJewelryPosition = "HealthMon_3D_Jewelry_LocalPositions_v1";
    private const string ActiveKey = "HealthMon_Roster_Selected_v1";
    private const string OfflineOwned = "HealthMonShop_OfflineOwned_v1";
    private const string ShopSelected = "HealthMonShop_OfflineSelectedPet_v1";
    private const string DataPrefix = "HealthMon_Roster_Data_v1_";
    private const string JewelryPrefix = "HealthMon_Roster_Jewelry_v1_";
    private const string PlacementPrefix = "HealthMon_Roster_JewelryPlacement_v1_";

    public HealthMonCharacterRosterAsset catalog;
    public PetStateManager state;
    public Transform homePetAnchor;
    public GameObject originalHomePet;
    [Header("Screens created by the installer")]
    public GameObject overlay, listPage, detailPage, confirmationPage;
    public HealthMonCharacterSlotCard cardTemplate;
    public RectTransform cardContent;
    public Button closeButton, backButton, detailBackButton, switchButton, cancelSwitchButton, confirmSwitchButton;
    public Button allFilterButton, ownedFilterButton, activeFilterButton, lockedFilterButton, shopButton;
    public Image detailPortrait, confirmBeforePortrait, confirmAfterPortrait;
    public TMP_Text bannerText, detailName, detailLevel, detailExp, detailStats, detailOutfit, detailTip, switchButtonText, confirmationText;
    public GameObject quickBar;
    public Button quickOpenButton;
    public Button[] quickButtons;
    public Image[] quickPortraits;
    public TMP_Text[] quickLabels;
    public Sprite quickActiveSprite, quickIdleSprite;
    public Sprite filterSelectedSprite, filterIdleSprite;

    [Serializable] private sealed class OwnedItems { public List<string> ids = new List<string>(); }
    [Serializable] private sealed class OutfitData
    {
        public bool necklaceUnlocked, earringUnlocked, pendantUnlocked, ringUnlocked;
        public bool necklaceEquipped, earringEquipped, pendantEquipped, ringEquipped;
    }

    private enum ListFilter { All, Owned, Active, Locked }
    private readonly List<HealthMonCharacterSlotCard> rendered = new List<HealthMonCharacterSlotCard>();
    private ListFilter filter = ListFilter.All;
    private HealthMonCharacterRosterAsset.Entry inspected;
    private string activeId;
    private bool ready;
    private bool switching;
    private GameObject liveVisual;
    private Renderer[] originalRenderers;
    private float nextWalletSync;
    private string lastShopSelection;

    private bool Offline => !CommonServerConnection.UsesServerAuthority;
    public string CurrentCharacterId => activeId;

    private IEnumerator Start()
    {
        // UIManager and PetStateManager must finish their Start() first.
        yield return null;
        if (state == null) state = FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        if (catalog == null || catalog.entries == null || catalog.entries.Count == 0 || state == null)
        {
            Debug.LogWarning("[Roster] 카탈로그 또는 PetStateManager가 없습니다.", this);
            yield break;
        }
        if (closeButton != null) closeButton.onClick.AddListener(Close);
        if (backButton != null) backButton.onClick.AddListener(ShowList);
        if (detailBackButton != null) detailBackButton.onClick.AddListener(ShowList);
        if (switchButton != null) switchButton.onClick.AddListener(RequestSwitch);
        if (cancelSwitchButton != null) cancelSwitchButton.onClick.AddListener(ShowDetail);
        if (confirmSwitchButton != null) confirmSwitchButton.onClick.AddListener(ConfirmSwitch);
        if (allFilterButton != null) allFilterButton.onClick.AddListener(() => SetFilter(ListFilter.All));
        if (ownedFilterButton != null) ownedFilterButton.onClick.AddListener(() => SetFilter(ListFilter.Owned));
        if (activeFilterButton != null) activeFilterButton.onClick.AddListener(() => SetFilter(ListFilter.Active));
        if (lockedFilterButton != null) lockedFilterButton.onClick.AddListener(() => SetFilter(ListFilter.Locked));
        if (shopButton != null) shopButton.onClick.AddListener(OpenShop);
        if (quickOpenButton != null) quickOpenButton.onClick.AddListener(Open);
        for (int i=0; quickButtons != null && i<quickButtons.Length;i++)
        {
            int index=i;
            if (quickButtons[i] != null) quickButtons[i].onClick.AddListener(() => OnQuickClicked(index));
        }
        if (cardTemplate != null) cardTemplate.gameObject.SetActive(false);
        if (overlay != null) overlay.SetActive(false);
        lastShopSelection = PlayerPrefs.GetString(ShopSelected, "");
        activeId = PlayerPrefs.GetString(ActiveKey, catalog.entries[0].id);
        // Honor an older offline-shop character selection on first roster install.
        if (!PlayerPrefs.HasKey(ActiveKey))
        {
            string previousShopSelection=PlayerPrefs.GetString(ShopSelected, "");
            foreach (var e in catalog.entries)
                if (e != null && e.shopItemId == previousShopSelection && IsOwned(e)) { activeId=e.id;break; }
        }
        if (GetEntry(activeId) == null || !IsOwned(GetEntry(activeId))) activeId = catalog.entries[0].id;
        if (homePetAnchor != null && originalHomePet != null)
            originalRenderers = originalHomePet.GetComponentsInChildren<Renderer>(true);
        if (Offline)
        {
            // One-time migration from the existing single-character profile.
            if (!PlayerPrefs.HasKey(DataPrefix + catalog.entries[0].id))
            {
                state.SavePetData();
                PlayerPrefs.SetString(DataPrefix + catalog.entries[0].id, PlayerPrefs.GetString(LegacyPet, ""));
                if (PlayerPrefs.HasKey(LegacyJewelry))
                    PlayerPrefs.SetString(JewelryPrefix + catalog.entries[0].id, PlayerPrefs.GetString(LegacyJewelry));
                if (PlayerPrefs.HasKey(LegacyJewelryPosition))
                    PlayerPrefs.SetString(PlacementPrefix + catalog.entries[0].id, PlayerPrefs.GetString(LegacyJewelryPosition));
                PlayerPrefs.Save();
            }
            LoadSlot(activeId, true);
        }
        ready = true;
        UpdateQuickBar();
    }

    private void Update()
    {
        if (!ready || !Offline || Time.unscaledTime < nextWalletSync) return;
        nextWalletSync = Time.unscaledTime + 2f;
        // Shop v3 stores selection as a product ID. When the player chooses an
        // already purchased pet in Shop, apply the same character in Home and
        // load that character's separate growth profile.
        string chosenInShop = PlayerPrefs.GetString(ShopSelected, "");
        if (!string.IsNullOrEmpty(chosenInShop) && chosenInShop != lastShopSelection)
        {
            lastShopSelection = chosenInShop;
            var purchased = FindByShopItem(chosenInShop);
            if (purchased != null && IsOwned(purchased) && purchased.id != activeId)
            {
                if (SwitchTo(purchased)) Debug.Log("[Roster] Shop-selected pet applied: " + purchased.title);
            }
        }
        if (quickBar != null && quickBar.activeInHierarchy) UpdateQuickBar();
    }

    private void OnApplicationPause(bool paused) { if (paused) SaveCurrent(); }
    private void OnApplicationQuit() { SaveCurrent(); }
    private void OnDisable() { SaveCurrent(); }

    private void SaveCurrent()
    {
        if (!ready || !Offline || state == null || string.IsNullOrEmpty(activeId)) return;
        state.SavePetData();
        string json = PlayerPrefs.GetString(LegacyPet, "");
        if (!string.IsNullOrEmpty(json)) PlayerPrefs.SetString(DataPrefix + activeId, json);
        if (PlayerPrefs.HasKey(LegacyJewelry))
            PlayerPrefs.SetString(JewelryPrefix + activeId, PlayerPrefs.GetString(LegacyJewelry));
        if (PlayerPrefs.HasKey(LegacyJewelryPosition))
            PlayerPrefs.SetString(PlacementPrefix + activeId, PlayerPrefs.GetString(LegacyJewelryPosition));
        PlayerPrefs.SetString(ActiveKey, activeId);
        PlayerPrefs.Save();
    }

    public void Open()
    {
        if (!ready || overlay == null) return;
        SaveCurrent();
        overlay.SetActive(true);
        ShowList();
    }
    public void Close()
    {
        if (overlay != null) overlay.SetActive(false);
        inspected = null;
    }

    private HealthMonCharacterRosterAsset.Entry FindByShopItem(string itemId)
    {
        if (catalog == null || catalog.entries == null) return null;
        if (itemId == "pet_starter") return catalog.entries.Count > 0 ? catalog.entries[0] : null;
        foreach (var e in catalog.entries)
            if (e != null && e.shopItemId == itemId) return e;
        return null;
    }

    private HealthMonCharacterRosterAsset.Entry GetEntry(string id)
    {
        if (catalog == null || catalog.entries == null) return null;
        foreach (var e in catalog.entries) if (e != null && e.id == id) return e;
        return null;
    }
    private bool IsOwned(HealthMonCharacterRosterAsset.Entry e)
    {
        if (e == null) return false;
        if (e.includedByDefault && catalog != null && catalog.entries.Count > 0 && e.id == catalog.entries[0].id) return true;
        if (string.IsNullOrEmpty(e.shopItemId)) return false;
        try
        {
            var ownership = JsonUtility.FromJson<OwnedItems>(PlayerPrefs.GetString(OfflineOwned, ""));
            return ownership != null && ownership.ids != null && ownership.ids.Contains(e.shopItemId);
        }
        catch { return false; }
    }

    private void SetFilter(ListFilter f) { filter=f; ShowList(); }
    private void UpdateFilterButtons()
    {
        var buttons=new[]{ allFilterButton,ownedFilterButton,activeFilterButton,lockedFilterButton };
        for(int i=0;i<buttons.Length;i++)
        {
            if(buttons[i]==null)continue;
            bool selected=(int)filter==i;
            var bg=buttons[i].targetGraphic as Image;
            if(bg!=null&&filterSelectedSprite!=null&&filterIdleSprite!=null)
            {
                bg.sprite=selected?filterSelectedSprite:filterIdleSprite;
                bg.type=Image.Type.Sliced;
            }
            var label=buttons[i].GetComponentInChildren<TMP_Text>();
            if(label!=null)label.color=selected?new Color(.04f,.23f,.32f):Color.white;
        }
    }
    public void ShowList()
    {
        if (listPage != null) listPage.SetActive(true);
        if (detailPage != null) detailPage.SetActive(false);
        if (confirmationPage != null) confirmationPage.SetActive(false);
        UpdateFilterButtons();
        RenderCards();
    }
    private void RenderCards()
    {
        if (cardContent == null || cardTemplate == null || catalog == null) return;
        foreach (var v in rendered) if (v != null) Destroy(v.gameObject);
        rendered.Clear();
        var visible = new List<HealthMonCharacterRosterAsset.Entry>();
        int ownedCount=0;
        foreach (var e in catalog.entries)
        {
            if (e == null) continue;
            bool owned=IsOwned(e);
            if (owned) ownedCount++;
            bool show=filter==ListFilter.All || (filter==ListFilter.Owned && owned) ||
                (filter==ListFilter.Active && e.id==activeId) || (filter==ListFilter.Locked && !owned);
            if (show) visible.Add(e);
        }
        if (bannerText != null) bannerText.text = Offline ?
            $"보유 {ownedCount} / {catalog.entries.Count}  ·  각 캐릭터를 따로 성장시켜 보세요" :
            "서버 계정의 캐릭터 전환은 아직 지원하지 않아요";
        const float cardWidth=455, cardHeight=510, gap=25;
        int rows=(visible.Count+1)/2;
        cardContent.sizeDelta = new Vector2(0, Math.Max(1,rows)*(cardHeight+gap)+30);
        for(int i=0;i<visible.Count;i++)
        {
            var entry=visible[i];
            var item=Instantiate(cardTemplate,cardContent,false);
            item.gameObject.SetActive(true);
            item.name="Slot_"+entry.id;
            var rt=item.transform as RectTransform;
            rt.anchorMin=rt.anchorMax=new Vector2(.5f,1);
            rt.pivot=new Vector2(.5f,1);rt.sizeDelta=new Vector2(cardWidth,cardHeight);
            rt.anchoredPosition=new Vector2(i%2==0?-241:241, -(i/2)*(cardHeight+gap)-14);
            bool owned=IsOwned(entry),active=entry.id==activeId;
            var p=GetSavedData(entry.id);
            string stats=owned?$"친밀도 {p.intimacy}  /  활동 {p.activity}":"상점에서 구매하여 해금";
            item.Bind(entry.title,owned?$"Lv. {p.level}":"잠긴 슬롯",stats,
                active?"육성 중":owned?"보유":"잠김", entry.portrait,active,!owned,()=>ShowEntry(entry));
            rendered.Add(item);
        }
    }

    private PetStateManager.PetSaveData DefaultData(string id)
    {
        return new PetStateManager.PetSaveData
        {
            petName=GetEntry(id)!=null?GetEntry(id).title:"헬스몬",
            level=1,currentExp=0,expToNextLevel=100,coin=state!=null?state.CurrentCoin:0,
            intimacy=25,activity=20,kindness=30,curiosity=20,growthStage="초기형"
        };
    }
    private PetStateManager.PetSaveData GetSavedData(string id)
    {
        if (state != null && id==activeId && Offline)
        {
            // Active snapshot includes live unsaved EXP/coins earned a moment ago.
            string current = PlayerPrefs.GetString(LegacyPet, "");
            if (!string.IsNullOrEmpty(current))
                try { var value=JsonUtility.FromJson<PetStateManager.PetSaveData>(current); if(value!=null) return value; } catch {}
        }
        var json=PlayerPrefs.GetString(DataPrefix+id, "");
        if(!string.IsNullOrEmpty(json))
            try { var value=JsonUtility.FromJson<PetStateManager.PetSaveData>(json); if(value!=null) return value; } catch {}
        return DefaultData(id);
    }

    private void ShowEntry(HealthMonCharacterRosterAsset.Entry e)
    {
        inspected=e;
        ShowDetail();
    }
    public void ShowDetail()
    {
        if(inspected==null) {ShowList();return;}
        if(listPage!=null)listPage.SetActive(false);
        if(confirmationPage!=null)confirmationPage.SetActive(false);
        if(detailPage!=null)detailPage.SetActive(true);
        var p=GetSavedData(inspected.id);
        if(detailPortrait!=null){detailPortrait.sprite=inspected.portrait;detailPortrait.preserveAspect=true;}
        if(detailName!=null)detailName.text=inspected.title;
        if(detailLevel!=null)detailLevel.text=$"Lv. {p.level} · {p.growthStage}";
        if(detailExp!=null)detailExp.text=$"EXP {p.currentExp:N0} / {Mathf.Max(1,p.expToNextLevel):N0}";
        if(detailStats!=null) detailStats.text=$"친밀도   {p.intimacy:00} / 100\n활동성   {p.activity:00} / 100\n다정함   {p.kindness:00} / 100\n호기심   {p.curiosity:00} / 100";
        if(detailOutfit!=null)
        {
            var outfit=GetOutfit(inspected.id);
            var equipped=new List<string>();
            if(outfit.necklaceEquipped) equipped.Add("목걸이");
            if(outfit.earringEquipped) equipped.Add("귀걸이");
            if(outfit.pendantEquipped) equipped.Add("펜던트");
            if(outfit.ringEquipped) equipped.Add("반지");
            detailOutfit.text="장착 중인 장신구  ·  "+(equipped.Count==0?"없음":string.Join(" · ",equipped));
        }
        bool owned=IsOwned(inspected), active=inspected.id==activeId;
        if (!owned)
        {
            if (detailLevel != null) detailLevel.text = "미보유 캐릭터";
            if (detailExp != null) detailExp.text = "구매 후 성장 시작";
            if (detailStats != null) detailStats.text = "상점에서 캐릭터를 구매하면\n이 슬롯의 육성 기록이 생성됩니다.";
            if (detailOutfit != null) detailOutfit.text = "장신구 정보 · 구매 후 확인 가능";
        }
        if(detailTip!=null)detailTip.text=!Offline?"서버 계정의 캐릭터 전환은 별도 연동이 필요합니다.":
            active?"지금 육성 중인 헬스몬입니다.":owned?"전환해도 각 캐릭터의 성장 기록은 유지됩니다.":"상점에서 구매하면 캐릭터 슬롯이 열립니다.";
        if(switchButtonText!=null)switchButtonText.text=active?"현재 육성 중":owned?"이 캐릭터로 전환":"상점에서 구매하기";
        if(switchButton!=null)switchButton.interactable=Offline&&!active;
    }

    public void RequestSwitch()
    {
        if(inspected==null || !Offline)return;
        if(!IsOwned(inspected)) { OpenShop(); return; }
        if(inspected.id==activeId)return;
        var before=GetEntry(activeId);
        if(confirmBeforePortrait!=null)confirmBeforePortrait.sprite=before!=null?before.portrait:null;
        if(confirmAfterPortrait!=null)confirmAfterPortrait.sprite=inspected.portrait;
        if(confirmationText!=null)confirmationText.text=$"{inspected.title}(으)로 전환할까요?\n\n레벨·EXP·스탯·착용 상태는 캐릭터별로 저장되고, 코인은 공유됩니다.";
        if(detailPage!=null)detailPage.SetActive(false);
        if(confirmationPage!=null)confirmationPage.SetActive(true);
    }

    public void ConfirmSwitch()
    {
        if(inspected==null||switching||!Offline||!IsOwned(inspected))return;
        switching=true;
        bool ok=SwitchTo(inspected);
        switching=false;
        if(ok) {Close();UpdateQuickBar();}
        else {if(confirmationText!=null)confirmationText.text="프리팹 전환에 실패했어요. 기존 캐릭터를 유지합니다.";}
    }
    private bool SwitchTo(HealthMonCharacterRosterAsset.Entry target)
    {
        if(target==null || state==null || !IsOwned(target))return false;
        if(target.id==activeId)return true;
        if(target.visualPrefab==null && target!=catalog.entries[0]) return false;
        if(!ApplyHomeVisual(target))return false;
        SaveCurrent();
        var next=GetSavedData(target.id);
        next.coin=state.CurrentCoin; // One shared wallet for shop and all characters.
        string json=JsonUtility.ToJson(next);
        PlayerPrefs.SetString(LegacyPet,json);
        PlayerPrefs.SetString(DataPrefix+target.id,json);
        SetActiveOutfit(target.id);
        activeId=target.id;
        PlayerPrefs.SetString(ActiveKey,activeId);
        if(!string.IsNullOrEmpty(target.shopItemId))
        {
            PlayerPrefs.SetString(ShopSelected,target.shopItemId);
            lastShopSelection=target.shopItemId;
        }
        PlayerPrefs.Save();
        state.LoadPetData();
        state.RefreshAllUI();
        Debug.Log("[Roster] Switched to "+target.title);
        return true;
    }

    private bool ApplyHomeVisual(HealthMonCharacterRosterAsset.Entry entry)
    {
        if(homePetAnchor==null||originalHomePet==null)
        {
            Debug.LogWarning("[Roster] HomePetAnchor/HealthMon_Slime 연결 누락. Inspector에서 기존 홈 펫을 연결해 주세요.");
            return false;
        }
        if(entry==catalog.entries[0])
        {
            if(liveVisual!=null){Destroy(liveVisual);liveVisual=null;}
            RestoreOriginalRenderers(true);
            return true;
        }
        GameObject candidate=null;
        try
        {
            candidate=Instantiate(entry.visualPrefab,originalHomePet.transform.parent,false);
            candidate.name="HM_ActiveSlotVisual_"+entry.id;
            candidate.transform.localPosition=originalHomePet.transform.localPosition;
            candidate.transform.localRotation=originalHomePet.transform.localRotation;
            candidate.transform.localScale=originalHomePet.transform.localScale;
            // Keep HomeCamera culling mask compatibility (AR preview layers may be different).
            SetLayerRecursively(candidate.transform,originalHomePet.layer);
            foreach(var col in candidate.GetComponentsInChildren<Collider>(true)) col.enabled=false;
            foreach(var rb in candidate.GetComponentsInChildren<Rigidbody>(true))
            {rb.isKinematic=true;rb.useGravity=false;}
            // Normalize visual height to the original HomePetAnchor character.
            var a=FindBounds(originalHomePet.GetComponentsInChildren<Renderer>(true));
            var b=FindBounds(candidate.GetComponentsInChildren<Renderer>(true));
            if(a.size.sqrMagnitude>0.01f&&b.size.sqrMagnitude>0.01f)
            {
                float factor=Mathf.Clamp(a.size.y/Mathf.Max(.001f,b.size.y),.55f,1.85f);
                candidate.transform.localScale*=factor;
                // Keep new prefab centered where the original home pet was visible.
                var aligned=FindBounds(candidate.GetComponentsInChildren<Renderer>(true));
                candidate.transform.position += a.center-aligned.center;
            }
        }
        catch(Exception ex)
        {
            Debug.LogWarning("[Roster] Visual creation failed: "+ex.Message);
            if(candidate!=null)Destroy(candidate);
            return false;
        }
        if(liveVisual!=null)Destroy(liveVisual);
        liveVisual=candidate;
        RestoreOriginalRenderers(false);
        return true;
    }
    private static Bounds FindBounds(Renderer[] renderers)
    {
        Bounds b=new Bounds(Vector3.zero,Vector3.zero);bool first=true;
        foreach(var r in renderers)
        {
            if(r==null)continue;
            if(first){b=r.bounds;first=false;} else b.Encapsulate(r.bounds);
        }
        return b;
    }
    private void RestoreOriginalRenderers(bool visible)
    {
        if(originalRenderers==null) originalRenderers=originalHomePet.GetComponentsInChildren<Renderer>(true);
        foreach(var r in originalRenderers)if(r!=null)r.enabled=visible;
    }
    private static void SetLayerRecursively(Transform t,int layer)
    {
        t.gameObject.layer=layer;
        foreach(Transform child in t)SetLayerRecursively(child,layer);
    }
    private void LoadSlot(string id,bool initial)
    {
        if(!Offline||state==null)return;
        // The legacy save on the FIRST install always belongs to the original pet.
        // Do not mistakenly clone that profile into a newly selected shop character.
        var p=(id!=catalog.entries[0].id && !PlayerPrefs.HasKey(DataPrefix+id))
            ? DefaultData(id) : GetSavedData(id);
        // Make the restored character inherit the LAST shared coin balance, not an old snapshot.
        int sharedCoins=state.CurrentCoin;
        p.coin=sharedCoins;
        PlayerPrefs.SetString(LegacyPet,JsonUtility.ToJson(p));
        if(id!=catalog.entries[0].id)ApplyHomeVisual(GetEntry(id));
        SetActiveOutfit(id, true);
        state.LoadPetData();
    }

    private OutfitData GetOutfit(string id, bool slotSnapshot=false)
    {
        string json=(id==activeId && !slotSnapshot)?PlayerPrefs.GetString(LegacyJewelry,""):PlayerPrefs.GetString(JewelryPrefix+id,"");
        if(!string.IsNullOrEmpty(json))try{return JsonUtility.FromJson<OutfitData>(json)??new OutfitData{necklaceUnlocked=true};}catch{}
        return new OutfitData{necklaceUnlocked=true};
    }
    private void SetActiveOutfit(string id,bool restoring=false)
    {
        var next=GetOutfit(id,restoring);
        var previous=GetOutfit(activeId);
        // Shop ownership is global; independent EQUIPPED bits live per character.
        next.necklaceUnlocked=true;
        next.earringUnlocked|=previous.earringUnlocked;
        next.pendantUnlocked|=previous.pendantUnlocked;
        next.ringUnlocked|=previous.ringUnlocked;
        PlayerPrefs.SetString(LegacyJewelry,JsonUtility.ToJson(next));
        PlayerPrefs.SetString(JewelryPrefix+id,JsonUtility.ToJson(next));
        string positions=PlayerPrefs.GetString(PlacementPrefix+id,"");
        if(!string.IsNullOrEmpty(positions))PlayerPrefs.SetString(LegacyJewelryPosition,positions);
        else PlayerPrefs.DeleteKey(LegacyJewelryPosition);
        PlayerPrefs.Save();
        var custom=FindFirstObjectByType<CustomizationPrototype>(FindObjectsInactive.Include);
        InvokePrivate(custom,"LoadCustomizationData");InvokePrivate(custom,"RefreshUI");
        foreach(var component in FindObjectsByType<HealthMon3DJewelryRig>(FindObjectsInactive.Include))
        {InvokePrivate(component,"LoadTransforms");component.RefreshVisible();}
        foreach(var component in FindObjectsByType<HealthMonAccessoryView>(FindObjectsInactive.Include))
            InvokePrivate(component,"RefreshEquipment");
    }
    private static void InvokePrivate(Component component,string method)
    {
        if(component==null)return;
        try{component.GetType().GetMethod(method,BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)?.Invoke(component,null);}
        catch(Exception e){Debug.LogWarning("[Roster] "+method+" reload skipped: "+e.Message);}
    }

    private void OpenShop()
    {
        Close();
        // Optional compatibility: no hard dependency on the separate shop package.
        var shopType=Type.GetType("HealthMonShopScreen, Assembly-CSharp");
        if(shopType!=null)
        {
            var shop=FindFirstObjectByType(shopType,FindObjectsInactive.Include) as Component;
            if(shop!=null)
            {
                var open=shopType.GetMethod("OpenShop",BindingFlags.Public|BindingFlags.Instance);
                open?.Invoke(shop,null);
                // Open the character category directly instead of making the
                // user search the accessory tab for a locked character.
                var tab=shopType.GetField("charactersTab",BindingFlags.Public|BindingFlags.Instance)?.GetValue(shop) as Button;
                if(tab!=null)tab.onClick.Invoke();
                return;
            }
        }
        Debug.Log("[Roster] 상점을 설치하면 구매 버튼이 상점을 엽니다.");
    }

    private void OnQuickClicked(int index)
    {
        var owned=new List<HealthMonCharacterRosterAsset.Entry>();
        if(catalog!=null)foreach(var e in catalog.entries)if(IsOwned(e))owned.Add(e);
        if(index<0 || index>=owned.Count)return;
        Open();ShowEntry(owned[index]);
    }
    private void UpdateQuickBar()
    {
        if(quickBar==null||catalog==null)return;
        var owned=new List<HealthMonCharacterRosterAsset.Entry>();
        foreach(var e in catalog.entries)if(IsOwned(e))owned.Add(e);
        for(int i=0;quickButtons!=null&&i<quickButtons.Length;i++)
        {
            bool visible=i<owned.Count;
            if(quickButtons[i]!=null)
            {
                quickButtons[i].gameObject.SetActive(visible);
                var bg=quickButtons[i].targetGraphic as Image;
                if(bg!=null){bg.sprite=visible&&owned[i].id==activeId?quickActiveSprite:quickIdleSprite;bg.type=Image.Type.Sliced;}
            }
            if(visible&&quickPortraits!=null&&i<quickPortraits.Length&&quickPortraits[i]!=null)
                quickPortraits[i].sprite=owned[i].portrait;
            if(visible&&quickLabels!=null&&i<quickLabels.Length&&quickLabels[i]!=null)
                quickLabels[i].text=owned[i].title;
        }
    }
}
