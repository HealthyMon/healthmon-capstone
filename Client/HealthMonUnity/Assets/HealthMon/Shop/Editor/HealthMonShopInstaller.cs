#if UNITY_EDITOR
using System;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public static class HealthMonShopInstaller
{
    private const string Root = "Assets/HealthMon/Shop";
    private const string CatalogPath = Root + "/HealthMonShopCatalog.asset";
    private static TMP_FontAsset font;

    [MenuItem("Tools/HealthMon/Shop/1. Shop UI 설치 (씬 백업 후)")]
    public static void Install()
    {
        if (EditorApplication.isPlaying)
        {
            EditorUtility.DisplayDialog("HealthMon Shop", "Play 모드를 종료한 뒤 실행하세요.", "확인");
            return;
        }
        Canvas canvas = FindMainCanvas();
        if (canvas == null)
        {
            EditorUtility.DisplayDialog("HealthMon Shop", "MainARScene에서 UI → Canvas → HomePanel 구조를 찾지 못했어요.", "확인");
            return;
        }
        if (canvas.transform.Find("HealthMonShopUI") != null)
        {
            if (!EditorUtility.DisplayDialog("HealthMon Shop", "기존 HealthMonShopUI를 교체할까요? 상점 UI만 새로 만듭니다.", "교체", "취소")) return;
        }
        SaveSceneBackup();
        EnsureSpriteImports();
        font = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>("Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold SDF.asset");
        if (font == null)
        {
            var found = AssetDatabase.FindAssets("t:TMP_FontAsset");
            if (found.Length > 0) font = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(AssetDatabase.GUIDToAssetPath(found[0]));
        }
        if (font == null)
        {
            EditorUtility.DisplayDialog("HealthMon Shop", "TextMeshPro 폰트 에셋을 찾지 못했어요. TMP Essential Resources를 먼저 설치하세요.", "확인");
            return;
        }
        var catalog = CreateCatalog();
        Transform previous = canvas.transform.Find("HealthMonShopUI");
        if (previous != null) UnityEngine.Object.DestroyImmediate(previous.gameObject);
        var home = canvas.transform.Find("HomePanel");
        if (home == null)
        {
            EditorUtility.DisplayDialog("HealthMon Shop", "HomePanel을 찾을 수 없어요. 설치를 취소했어요.", "확인");
            return;
        }
        Transform oldButton = home.Find("HM_OpenShop_Button");
        if (oldButton != null) UnityEngine.Object.DestroyImmediate(oldButton.gameObject);
        var controllerRoot = CreateRect("HealthMonShopUI", canvas.transform);
        Stretch(controllerRoot);
        var shop = controllerRoot.gameObject.AddComponent<HealthMonShopScreen>();
        shop.catalog = catalog;
        BuildScreen(controllerRoot, shop);
        controllerRoot.SetAsLastSibling();
        var open = CreateButton("HM_OpenShop_Button", home, 180, 75, Sprite("ShopButtonGold"), "상점", 33, new Color(.13f,.23f,.47f));
        var rt = open.transform as RectTransform;
        rt.anchorMin = rt.anchorMax = new Vector2(1,1); rt.pivot = new Vector2(1,1);
        rt.anchoredPosition = new Vector2(-22,-375); // Above existing BottomNavV2, without replacing navigation
        UnityEventTools.AddPersistentListener(open.onClick, shop.OpenShop);
        EditorUtility.SetDirty(open);
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        Selection.activeObject = shop.gameObject;
        EditorUtility.DisplayDialog("HealthMon Shop", "상점 UI가 생성됐습니다. HomePanel의 '상점' 버튼으로 열어보세요.\n\n현재 서버에는 구매 API가 없어, 결제는 연결 전까지 비활성화됩니다.", "확인");
    }

    [MenuItem("Tools/HealthMon/Shop/2. Shop UI 제거 (카탈로그 유지)")]
    public static void Uninstall()
    {
        if (EditorApplication.isPlaying) return;
        var canvas = FindMainCanvas();
        if (canvas == null) return;
        SaveSceneBackup();
        var shop = canvas.transform.Find("HealthMonShopUI");
        if (shop != null) UnityEngine.Object.DestroyImmediate(shop.gameObject);
        var btn = canvas.transform.Find("HomePanel/HM_OpenShop_Button");
        if (btn != null) UnityEngine.Object.DestroyImmediate(btn.gameObject);
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        EditorUtility.DisplayDialog("HealthMon Shop", "상점 UI와 상점 진입 버튼만 제거했습니다.", "확인");
    }

    [MenuItem("Tools/HealthMon/Shop/3. 백업 폴더 열기")]
    private static void OpenBackups()
    {
        var path = Path.GetFullPath(Root + "/Backups");
        if (!Directory.Exists(path)) Directory.CreateDirectory(path);
        EditorUtility.RevealInFinder(path);
    }

    private static void SaveSceneBackup()
    {
        var scene = SceneManager.GetActiveScene();
        if (!scene.IsValid() || string.IsNullOrEmpty(scene.path))
            throw new InvalidOperationException("현재 씬을 먼저 저장해야 합니다.");
        EditorSceneManager.SaveScene(scene);
        EnsureFolder(Root + "/Backups");
        string stem = Path.GetFileNameWithoutExtension(scene.path);
        string dest = Root + "/Backups/" + stem + "_BeforeShop_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".unity";
        if (!AssetDatabase.CopyAsset(scene.path, dest))
            throw new InvalidOperationException("씬 백업에 실패했습니다. 설치를 중단합니다.");
        AssetDatabase.Refresh();
        Debug.Log("[Shop] Scene backup: " + dest);
    }

    private static Canvas FindMainCanvas()
    {
        foreach (var c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (c.transform.Find("HomePanel") != null && c.transform.Find("DialoguePanel") != null)
                return c;
        return null;
    }

    private static void EnsureFolder(string path)
    {
        string[] bits = path.Split('/');
        string current = bits[0];
        for (int i=1; i<bits.Length; i++)
        {
            string next = current + "/" + bits[i];
            if (!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(current, bits[i]);
            current = next;
        }
    }

    private static void EnsureSpriteImports()
    {
        string dir = Root + "/Sprites";
        foreach (string absolute in Directory.GetFiles(dir, "*.png"))
        {
            string path = absolute.Replace('\\','/');
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) continue;
            bool changed = false;
            if (importer.textureType != TextureImporterType.Sprite) { importer.textureType = TextureImporterType.Sprite; changed = true; }
            if (importer.alphaIsTransparency == false) { importer.alphaIsTransparency = true; changed = true; }
            var border = importer.spriteBorder;
            bool sliced = Path.GetFileNameWithoutExtension(path).StartsWith("Shop") &&
                !path.EndsWith("ShopBackground.png") && !path.EndsWith("ShopPill.png");
            Vector4 expected = sliced ? new Vector4(35,35,35,35) : Vector4.zero;
            if (border != expected) { importer.spriteBorder = expected; changed = true; }
            if (changed) importer.SaveAndReimport();
        }
    }

    private static Sprite Sprite(string key)
    {
        return AssetDatabase.LoadAssetAtPath<Sprite>(Root + "/Sprites/" + key + ".png");
    }

    private static HealthMonShopCatalog CreateCatalog()
    {
        var existing = AssetDatabase.LoadAssetAtPath<HealthMonShopCatalog>(CatalogPath);
        if (existing != null) return existing; // user-adjusted prices are preserved on reinstall.
        var catalog = ScriptableObject.CreateInstance<HealthMonShopCatalog>();
        Add(catalog,"jewelry_necklace","기본 목걸이","헬스몬과 처음부터 함께하는 장신구예요.",HealthMonShopCategory.Accessory,0,"IconNecklace",true,"목걸이");
        Add(catalog,"jewelry_earring","반짝 귀걸이","귀 주변을 화사하게 꾸미는 장신구예요.",HealthMonShopCategory.Accessory,120,"IconEarring",false,"귀걸이");
        Add(catalog,"jewelry_pendant","별빛 펜던트","헬스몬의 특별한 날에 어울리는 펜던트예요.",HealthMonShopCategory.Accessory,180,"IconPendant",false,"펜던트");
        Add(catalog,"jewelry_ring","빛의 반지","반짝이는 보석이 달린 작은 반지예요.",HealthMonShopCategory.Accessory,160,"IconRing",false,"반지");
        Add(catalog,"pet_starter","기본 헬스몬","처음 만나는 친구. 기본 보유 캐릭터예요.",HealthMonShopCategory.Character,0,"IconPetStarter",true,null);
        Add(catalog,"pet_mint","민트 헬스몬","새로운 펫을 구매하고 별도로 성장시켜 보세요.",HealthMonShopCategory.Character,450,"IconPetMint",false,null);
        Add(catalog,"pet_lavender","라벤더 헬스몬","새로운 펫을 구매하고 별도로 성장시켜 보세요.",HealthMonShopCategory.Character,650,"IconPetLavender",false,null);
        AssetDatabase.CreateAsset(catalog,CatalogPath);
        AssetDatabase.SaveAssets();
        return catalog;
    }
    private static void Add(HealthMonShopCatalog c,string id,string title,string desc,HealthMonShopCategory cat,int coin,string icon,bool initial,string jewelry)
    {
        c.items.Add(new HealthMonShopItem {itemId=id,displayName=title,description=desc,category=cat,
            displayCoinPrice=coin,icon=Sprite(icon),includedByDefault=initial,
            featured=id=="jewelry_pendant" || id=="pet_lavender",jewelryName=jewelry});
    }

    private static RectTransform CreateRect(string name,Transform parent)
    {
        var go=new GameObject(name,typeof(RectTransform));
        go.transform.SetParent(parent,false);
        return (RectTransform)go.transform;
    }
    private static void Stretch(RectTransform t)
    {
        t.anchorMin=Vector2.zero; t.anchorMax=Vector2.one; t.pivot=new Vector2(.5f,.5f);
        t.offsetMin=Vector2.zero;t.offsetMax=Vector2.zero;
    }
    private static RectTransform AtTop(string name,Transform parent,float x,float y,float w,float h)
    {
        var t=CreateRect(name,parent);t.anchorMin=t.anchorMax=new Vector2(.5f,1f);
        t.pivot=new Vector2(.5f,.5f);t.sizeDelta=new Vector2(w,h);t.anchoredPosition=new Vector2(x,y);return t;
    }
    private static RectTransform AtBottom(string name,Transform parent,float x,float y,float w,float h)
    {
        var t=CreateRect(name,parent);t.anchorMin=t.anchorMax=new Vector2(.5f,0f);
        t.pivot=new Vector2(.5f,.5f);t.sizeDelta=new Vector2(w,h);t.anchoredPosition=new Vector2(x,y);return t;
    }
    private static Image ImageOn(RectTransform t,Sprite sprite,Color color,bool sliced=true)
    {
        var img=t.gameObject.AddComponent<Image>();img.sprite=sprite;img.color=color;
        img.type=sliced && sprite!=null ? Image.Type.Sliced : Image.Type.Simple;
        img.raycastTarget=true;return img;
    }
    private static TMP_Text Text(Transform parent,string name,string value,int size,Color color,
        TextAlignmentOptions align,float x,float y,float w,float h,bool bottom=false)
    {
        var t=bottom? AtBottom(name,parent,x,y,w,h):AtTop(name,parent,x,y,w,h);
        var text=t.gameObject.AddComponent<TextMeshProUGUI>();text.font=font;text.fontSize=size;
        text.text=value;text.color=color;text.alignment=align;text.enableWordWrapping=true;
        text.raycastTarget=false;text.overflowMode=TextOverflowModes.Ellipsis;
        text.margin=new Vector4(4,2,4,2);
        return text;
    }
    private static Button CreateButton(string name,Transform parent,float w,float h,Sprite bg,string label,int size,Color ink)
    {
        var t=AtTop(name,parent,0,0,w,h);var img=ImageOn(t,bg,Color.white);
        var b=t.gameObject.AddComponent<Button>();b.targetGraphic=img;b.transition=Selectable.Transition.ColorTint;
        var text=Text(t,"Label",label,size,ink,TextAlignmentOptions.Center,0,-h/2,w-18,h-12);
        return b;
    }
    private static Color C(string hex)
    {
        ColorUtility.TryParseHtmlString(hex,out var color);return color;
    }

    private static void BuildScreen(RectTransform root,HealthMonShopScreen shop)
    {
        var overlay=CreateRect("ShopOverlay",root);Stretch(overlay);
        var cv=overlay.gameObject.AddComponent<Canvas>();cv.overrideSorting=true;cv.sortingOrder=500;
        overlay.gameObject.AddComponent<GraphicRaycaster>();
        ImageOn(overlay,Sprite("ShopBackground"),Color.white,false);
        shop.overlay=overlay.gameObject;

        var banner=AtTop("ShopBanner",overlay,0,-418,970,135);
        ImageOn(banner,Sprite("ShopCardRare"),Color.white);
        Text(banner,"BannerTitle","헬스몬 상점",37,C("#FFF5D6"),TextAlignmentOptions.Center,0,-48,900,51);
        Text(banner,"BannerSubtitle","장신구와 새로운 친구를 만나보세요!",24,C("#D4EBFF"),TextAlignmentOptions.Center,0,-99,900,37);
        var top=AtTop("ShopHeader",overlay,0,-118,1010,176);ImageOn(top,Sprite("ShopTopBar"),Color.white);
        Text(top,"Brand","HEALTHMON",20,C("#B6F5E9"),TextAlignmentOptions.Left,-298,-39,360,39);
        Text(top,"ShopTitle","헬스몬 상점",50,Color.white,TextAlignmentOptions.Left,-245,-94,460,68);
        var coinLabel=Text(top,"Balance","코인 --",36,C("#FFF3AF"),TextAlignmentOptions.Center,320,-91,220,60);
        shop.currencyLabel=coinLabel;
        var coin=AtTop("CoinIcon",top,207,-90,48,48);ImageOn(coin,Sprite("IconCoin"),Color.white,false).raycastTarget=false;
        var close=CreateButton("CloseShop",top,82,80,Sprite("ShopTabOff"),"×",52,Color.white);
        (close.transform as RectTransform).anchoredPosition=new Vector2(462,-86);shop.closeButton=close;

        var tabA=CreateButton("AccessoryTab",overlay,468,96,Sprite("ShopTabOn"),"장신구",34,Color.white);
        (tabA.transform as RectTransform).anchoredPosition=new Vector2(-244,-298);shop.accessoriesTab=tabA;
        var tabB=CreateButton("CharacterTab",overlay,468,96,Sprite("ShopTabOff"),"새 캐릭터",34,Color.white);
        (tabB.transform as RectTransform).anchoredPosition=new Vector2(244,-298);shop.charactersTab=tabB;
        shop.selectedTabSprite=Sprite("ShopTabOn");
        shop.unselectedTabSprite=Sprite("ShopTabOff");
        Text(overlay,"ShopHint","상품을 선택해 보세요",23,C("#D4EFFF"),TextAlignmentOptions.Center,0,-610,950,44);
        var filterHolder=AtTop("CategoryFilters",overlay,0,-533,970,58);
        string[] names={"전체","목걸이","귀걸이","펜던트","반지"};
        Button[] filterButtons=new Button[names.Length];
        for (int i=0;i<names.Length;i++)
        {
            filterButtons[i]=CreateButton("Filter_"+names[i],filterHolder,179,57,Sprite("ShopPill"),names[i],23,C("#EFFFFF"));
            (filterButtons[i].transform as RectTransform).anchoredPosition=new Vector2(-383+i*192,-31);
        }
        shop.filterAll=filterButtons[0];shop.filterNecklace=filterButtons[1];shop.filterEarring=filterButtons[2];
        shop.filterPendant=filterButtons[3];shop.filterRing=filterButtons[4];
        shop.filterStatus=Text(overlay,"FilterStatus","전체 장신구",25,C("#C8E9FD"),TextAlignmentOptions.Left,-315,-664,450,40);
        shop.hintLabel=overlay.Find("ShopHint").GetComponent<TMP_Text>();

        var list=CreateRect("ProductList",overlay);list.anchorMin=Vector2.zero;list.anchorMax=Vector2.one;
        list.offsetMin=new Vector2(42,310);list.offsetMax=new Vector2(-42,-705);
        var scroll=list.gameObject.AddComponent<ScrollRect>();scroll.horizontal=false;scroll.vertical=true;
        scroll.movementType=ScrollRect.MovementType.Clamped;scroll.scrollSensitivity=36f;
        var viewport=CreateRect("Viewport",list);Stretch(viewport);
        viewport.gameObject.AddComponent<RectMask2D>();
        scroll.viewport=viewport;
        var content=CreateRect("Content",viewport);content.anchorMin=new Vector2(0,1);content.anchorMax=new Vector2(1,1);
        content.pivot=new Vector2(.5f,1f);content.anchoredPosition=Vector2.zero;
        content.sizeDelta=new Vector2(0,740);
        shop.content=content;shop.scrollRect=scroll;scroll.content=content;

        var card=AtTop("_CardTemplate",content,0,0,446,350);
        var cardBg=ImageOn(card,Sprite("ShopCard"),Color.white);
        var cardButton=card.gameObject.AddComponent<Button>();cardButton.targetGraphic=cardBg;
        var title=Text(card,"Name","별빛 펜던트",37,Color.white,TextAlignmentOptions.Center,0,-236,410,55);
        var subtitle=Text(card,"Category","장신구",23,C("#B9E6FF"),TextAlignmentOptions.Center,0,-281,410,35);
        var price=Text(card,"Price","180 C",30,C("#FFE8A9"),TextAlignmentOptions.Center,0,-324,410,44);
        var picture=AtTop("ItemIcon",card,0,-120,178,178);
        var pic=ImageOn(picture,Sprite("IconPendant"),Color.white,false);pic.raycastTarget=false;
        var cardview=card.gameObject.AddComponent<HealthMonShopProductCard>();
        cardview.icon=pic;cardview.cardBackground=cardBg;
        cardview.normalBackground=Sprite("ShopCard");cardview.featuredBackground=Sprite("ShopCardRare");
        cardview.nameLabel=title;
        cardview.subtitleLabel=subtitle;cardview.priceLabel=price;cardview.cardButton=cardButton;
        shop.cardTemplate=cardview;card.gameObject.SetActive(false);

        var bottom=AtBottom("SelectionPanel",overlay,0,146,1010,260);
        ImageOn(bottom,Sprite("ShopModal"),Color.white);
        var selectedIcon=AtBottom("SelectedIcon",bottom,-427,130,104,104);
        shop.selectedIcon=ImageOn(selectedIcon,Sprite("IconEarring"),Color.white,false);
        shop.selectedTitle=Text(bottom,"SelectedName","상품을 선택하세요",35,Color.white,TextAlignmentOptions.Left,-206,190,390,54,true);
        shop.selectedDescription=Text(bottom,"SelectedDescription","구매할 상품의 설명이 표시됩니다.",23,C("#D7EEFF"),TextAlignmentOptions.Left,-195,108,442,92,true);
        shop.selectedPrice=Text(bottom,"SelectedPrice","-- C",29,C("#FFE8A9"),TextAlignmentOptions.Center,342,202,278,43,true);
        var purchase=CreateButton("Purchase",bottom,294,107,Sprite("ShopButtonMint"),"구매하기",30,C("#132B50"));
        (purchase.transform as RectTransform).anchorMin=(purchase.transform as RectTransform).anchorMax=new Vector2(.5f,0);
        (purchase.transform as RectTransform).anchoredPosition=new Vector2(325,99);
        shop.actionButton=purchase;
        shop.actionText=purchase.GetComponentInChildren<TMP_Text>();
        Text(overlay,"Disclaimer","실제 결제·해금은 서버 승인 후 반영됩니다.",21,C("#B7D5F3"),TextAlignmentOptions.Center,0,18,820,40,true);

        var success=CreateRect("PurchaseSuccessModal",overlay);Stretch(success);
        ImageOn(success,null,new Color(.02f,.04f,.13f,.87f),false);
        shop.successPanel=success.gameObject;
        var successCard=CreateRect("SuccessCard",success);
        successCard.anchorMin=successCard.anchorMax=new Vector2(.5f,.5f);successCard.pivot=new Vector2(.5f,.5f);
        successCard.sizeDelta=new Vector2(850,720);successCard.anchoredPosition=Vector2.zero;
        ImageOn(successCard,Sprite("ShopModal"),Color.white);
        shop.successTitle=Text(successCard,"SuccessTitle","구매 완료!",56,C("#FFF0AC"),TextAlignmentOptions.Center,0,-96,720,90);
        var successIconRect=AtTop("SuccessIcon",successCard,0,-292,240,240);
        shop.successIcon=ImageOn(successIconRect,Sprite("IconEarring"),Color.white,false);
        shop.successDescription=Text(successCard,"SuccessMessage","새 아이템을 획득했어요!",34,Color.white,TextAlignmentOptions.Center,0,-474,750,92);
        shop.successCloseButton=CreateButton("SuccessContinue",successCard,430,108,Sprite("ShopButtonGold"),"계속 쇼핑하기",34,C("#1F3357"));
        (shop.successCloseButton.transform as RectTransform).anchoredPosition=new Vector2(0,-642);
        success.gameObject.SetActive(false);

        var modal=CreateRect("PurchaseConfirmModal",overlay);Stretch(modal);
        ImageOn(modal,null,new Color(.02f,.06f,.16f,.85f),false);
        shop.confirmPanel=modal.gameObject;
        var box=AtTop("ConfirmCard",modal,0,0,850,540);
        box.anchorMin=box.anchorMax=new Vector2(.5f,.5f);box.anchoredPosition=Vector2.zero;
        ImageOn(box,Sprite("ShopModal"),Color.white);
        Text(box,"ModalTitle","구매 확인",50,Color.white,TextAlignmentOptions.Center,0,-102,770,90);
        shop.confirmText=Text(box,"ModalMessage","구매할까요?",34,C("#E7F7FF"),TextAlignmentOptions.Center,0,-245,720,165);
        var yes=CreateButton("ConfirmPurchase",box,320,106,Sprite("ShopButtonGold"),"구매 확인",34,C("#1F3357"));
        (yes.transform as RectTransform).anchoredPosition=new Vector2(-180,-437);shop.confirmButton=yes;
        var cancel=CreateButton("CancelPurchase",box,320,106,Sprite("ShopButtonBlue"),"취소",34,Color.white);
        (cancel.transform as RectTransform).anchoredPosition=new Vector2(180,-437);shop.cancelButton=cancel;
        modal.gameObject.SetActive(false);
        overlay.gameObject.SetActive(false);
    }
}
#endif
