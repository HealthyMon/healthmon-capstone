#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.UI;

public static class HealthMonCharacterRosterInstaller
{
    private const string Root = "Assets/HealthMon/MultiCharacter";
    private const string AssetPath = Root + "/HealthMonCharacterRoster.asset";
    private const string FontPath = Root + "/Fonts/HealthMon_Roster_KoreanDynamic.asset";
    private static TMP_FontAsset font;
    private static readonly Color White = Color.white;
    private static Color C(string hex) { ColorUtility.TryParseHtmlString(hex,out var color);return color; }

    [MenuItem("Tools/HealthMon/Characters/0. 현재 씬 진단")]
    public static void Diagnose()
    {
        Canvas canvas=FindCanvas();
        Transform anchor=FindByName("HomePetAnchor");
        var state=UnityEngine.Object.FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        string msg="메인 Canvas: "+(canvas!=null?"확인":"없음")+"\n"+
            "PetStateManager: "+(state!=null?"확인":"없음")+"\n"+
            "HomePetAnchor: "+(anchor!=null?"확인":"없음")+"\n"+
            "홈 펫: "+(anchor!=null&&anchor.Find("HealthMon_Slime")!=null?"확인":"Inspector에서 수동 연결 필요")+"\n"+
            "Cute_Slime_N1: "+(AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Suriyun/Cute_Slime/Prefab/Cute_Slime_N1.prefab")!=null?"확인":"없음")+"\n"+
            "Maplestory Bold: "+(AssetDatabase.LoadAssetAtPath<Font>("Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold.ttf")!=null?"확인":"없음");
        Debug.Log("[Roster diagnosis]\n"+msg);
        EditorUtility.DisplayDialog("HealthMon Character Slot · 씬 진단",msg,"확인");
    }

    [MenuItem("Tools/HealthMon/Characters/1. 캐릭터 슬롯 UI 설치 (씬 백업)")]
    public static void Install()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode)
        { EditorUtility.DisplayDialog("HealthMon Characters","Play 모드를 종료하고 실행해 주세요.","확인");return; }
        Canvas canvas=FindCanvas();
        if(canvas==null) { EditorUtility.DisplayDialog("HealthMon Characters","MainARScene의 UI/Canvas/HomePanel을 찾지 못했어요.","확인");return; }
        var existing=canvas.transform.Find("HM_MultiCharacterSystem");
        if(existing!=null&&!EditorUtility.DisplayDialog("HealthMon Characters","이미 설치된 슬롯 UI를 교체할까요? 캐릭터별 PlayerPrefs 육성 데이터는 유지됩니다.","교체","취소"))return;
        try
        {
            // Import the art first, and DO NOT replace the current UI if a required sprite is missing.
            EnsureSpriteImports();
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            if (!ValidateSprites()) return;
            font = EnsureFont();
            if(font==null){EditorUtility.DisplayDialog("HealthMon Characters","TMP용 한글 폰트 생성 실패. Maplestory Bold.ttf 경로를 확인해 주세요.","확인");return;}
            // Make the scene backup only after the assets and font pass validation.
            SaveBackup();
            var asset=EnsureCatalog();
            if(existing!=null)UnityEngine.Object.DestroyImmediate(existing.gameObject);
            var home=canvas.transform.Find("HomePanel");
            if(home==null)return;
            var oldQuick=home.Find("HM_CharacterQuickBar");
            if(oldQuick!=null)UnityEngine.Object.DestroyImmediate(oldQuick.gameObject);
            var root=Rect("HM_MultiCharacterSystem",canvas.transform);Stretch(root);
            var controller=root.gameObject.AddComponent<HealthMonCharacterRosterController>();
            controller.catalog=asset;
            controller.state=UnityEngine.Object.FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
            Transform anchor=FindByName("HomePetAnchor");
            if(anchor!=null)
            {
                controller.homePetAnchor=anchor;
                Transform original=anchor.Find("HealthMon_Slime");
                if(original==null&&anchor.childCount>0)original=anchor.GetChild(0);
                if(original!=null)controller.originalHomePet=original.gameObject;
            }
            BuildRoster(root,controller);
            BuildQuickBar(home,controller);
            root.SetAsLastSibling();
            HealthMonCharacterPrefabPortraitBaker.Begin(asset);
            EditorUtility.SetDirty(controller);
            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            AssetDatabase.SaveAssets();
            Selection.activeObject=controller.gameObject;
            EditorUtility.DisplayDialog("HealthMon Characters", "캐릭터 슬롯 UI 설치 완료!\n\n홈에서 '캐릭터 슬롯' 버튼을 누르면 열립니다.\n코인은 공용, 레벨·EXP·스탯은 각자 저장됩니다.\n서버 권한 모드에서는 안전을 위해 전환이 잠겨 있습니다.","확인");
        }
        catch(Exception ex){Debug.LogException(ex);EditorUtility.DisplayDialog("HealthMon Characters","설치 중 오류: "+ex.Message+"\n씬 백업은 유지됩니다.","확인");}
    }

    [MenuItem("Tools/HealthMon/Characters/0-1. 캐릭터 UI 이미지 검사")]
    public static void ValidateSpriteMenu()
    {
        EnsureSpriteImports();
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        if (ValidateSprites()) EditorUtility.DisplayDialog("HealthMon Characters", "필수 UI 이미지 연결이 정상입니다.", "확인");
    }

    [MenuItem("Tools/HealthMon/Characters/6. 상점 구매 연동 + 프리팹 이미지 + 슬롯 UI 다시 설치")]
    public static void SyncShopAndRebuild() { Install(); }

    [MenuItem("Tools/HealthMon/Characters/2. 프리팹 실제 사진 생성 / 보완")]
    public static void BakePortraits()
    {
        var asset=EnsureCatalog();
        if(asset==null) { Debug.LogError("[Roster] 캐릭터 카탈로그 없음"); return; }
        HealthMonCharacterPrefabPortraitBaker.Begin(asset);
    }

    [MenuItem("Tools/HealthMon/Characters/3. 테스트용 두 번째 캐릭터 해금 (오프라인 전용)")]
    public static void GrantTestCharacter()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode){Debug.LogWarning("[Roster] Play를 꺼주세요.");return;}
        string key="HealthMonShop_OfflineOwned_v1";
        string id="prefab_cute_slime_n1";
        OwnedItems store=null;
        try{store=JsonUtility.FromJson<OwnedItems>(PlayerPrefs.GetString(key,""));}catch{}
        if(store==null||store.ids==null)store=new OwnedItems();
        if(!store.ids.Contains(id))store.ids.Add(id);
        PlayerPrefs.SetString(key,JsonUtility.ToJson(store));PlayerPrefs.Save();
        EditorUtility.DisplayDialog("HealthMon Characters","개발 테스트용 N1 캐릭터가 로컬 보유 목록에 추가됐습니다.\n실제 구매는 발생하지 않습니다.","확인");
    }
    [Serializable]private sealed class OwnedItems{public List<string> ids=new List<string>();}

    [MenuItem("Tools/HealthMon/Characters/4. 슬롯 UI 제거 (육성 저장 유지)")]
    public static void Uninstall()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode)return;
        var canvas=FindCanvas();if(canvas==null)return;
        SaveBackup();
        var v=canvas.transform.Find("HM_MultiCharacterSystem");if(v!=null)UnityEngine.Object.DestroyImmediate(v.gameObject);
        var home=canvas.transform.Find("HomePanel/HM_CharacterQuickBar");if(home!=null)UnityEngine.Object.DestroyImmediate(home.gameObject);
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        EditorUtility.DisplayDialog("HealthMon Characters","UI만 제거했습니다. 슬롯별 로컬 저장 데이터는 남아 있습니다.","확인");
    }

    [MenuItem("Tools/HealthMon/Characters/5. 백업 폴더 열기")]
    public static void ShowBackups(){EnsureFolder(Root+"/Backups");EditorUtility.RevealInFinder(Path.GetFullPath(Root+"/Backups"));}

    private static Canvas FindCanvas()
    {
        foreach(var c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include,FindObjectsSortMode.None))
            if(c.transform.Find("HomePanel")!=null&&c.transform.Find("DialoguePanel")!=null)return c;
        return null;
    }
    private static Transform FindByName(string name)
    {
        foreach(var t in UnityEngine.Object.FindObjectsByType<Transform>(FindObjectsInactive.Include,FindObjectsSortMode.None))
            if(t.name==name)return t;
        return null;
    }
    private static void EnsureFolder(string path)
    {
        var parts=path.Replace('\\','/').Split('/');string cursor=parts[0];
        for(int i=1;i<parts.Length;i++){string p=cursor+"/"+parts[i];if(!AssetDatabase.IsValidFolder(p))AssetDatabase.CreateFolder(cursor,parts[i]);cursor=p;}
    }
    private static void SaveBackup()
    {
        var scene=SceneManager.GetActiveScene();
        if(!scene.IsValid()||string.IsNullOrEmpty(scene.path))throw new InvalidOperationException("현재 씬을 먼저 저장해 주세요.");
        EditorSceneManager.SaveScene(scene);EnsureFolder(Root+"/Backups");
        string filename=Root+"/Backups/"+Path.GetFileNameWithoutExtension(scene.path)+"_BeforeCharacter_"+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".unity";
        if(!AssetDatabase.CopyAsset(scene.path,filename))throw new InvalidOperationException("씬 백업에 실패하여 설치를 취소합니다.");
        Debug.Log("[Roster] Backup saved: "+filename);
    }
    private static void EnsureSpriteImports()
    {
        string path=Root+"/Sprites";
        foreach(var filename in Directory.GetFiles(path,"*.png"))
        {
            string assetPath=filename.Replace('\\','/');
            var importer=AssetImporter.GetAtPath(assetPath) as TextureImporter;
            if(importer==null)continue;
            bool portrait=Path.GetFileName(assetPath).Contains("Avatar_")||Path.GetFileName(assetPath).Contains("Icon")||Path.GetFileName(assetPath).Contains("Backdrop");
            var border=portrait?Vector4.zero:new Vector4(34,34,34,34);
            bool dirty=importer.textureType!=TextureImporterType.Sprite||importer.spriteBorder!=border||!importer.alphaIsTransparency;
            if(dirty){importer.textureType=TextureImporterType.Sprite;importer.spriteBorder=border;importer.alphaIsTransparency=true;importer.SaveAndReimport();}
        }
    }
    // Unity sometimes imports freshly copied PNGs as Default textures on the first pass.
    // Resolve the exact sprite instead of creating blank white UI Images.
    private static Sprite S(string key)
    {
        string path = Root + "/Sprites/" + key + ".png";
        Sprite result = AssetDatabase.LoadAssetAtPath<Sprite>(path);
        if (result != null) return result;

        if (AssetDatabase.LoadAssetAtPath<Texture2D>(path) != null)
        {
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer != null && importer.textureType != TextureImporterType.Sprite)
            {
                importer.textureType = TextureImporterType.Sprite;
                importer.spriteImportMode = SpriteImportMode.Single;
                importer.alphaIsTransparency = true;
                importer.SaveAndReimport();
            }
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
            result = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (result != null) return result;
            foreach (var o in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                result = o as Sprite;
                if (result != null) return result;
            }
        }

        // Fallback for installations where the sprite package was moved inside Assets.
        foreach (string guid in AssetDatabase.FindAssets(key + " t:Sprite", new [] { "Assets/HealthMon" }))
        {
            string foundPath = AssetDatabase.GUIDToAssetPath(guid);
            if (Path.GetFileNameWithoutExtension(foundPath) != key) continue;
            result = AssetDatabase.LoadAssetAtPath<Sprite>(foundPath);
            if (result != null) return result;
        }
        Debug.LogError("[HealthMon Roster] Missing sprite: " + key + " (expected " + path + ")");
        return null;
    }

    // Abort BEFORE deleting any existing UI if the sprite imports failed.
    private static bool ValidateSprites()
    {
        string[] required = {
            "MC_Backdrop", "MC_Header", "MC_Card", "MC_ActiveCard", "MC_LockedCard",
            "MC_Panel", "MC_DetailPanel", "MC_StatPanel", "MC_ConfirmPanel",
            "MC_ButtonGold", "MC_ButtonBlue", "MC_ButtonDark", "MC_ButtonMint",
            "MC_TabActive", "MC_TabInactive", "MC_QuickBar", "MC_SmallChip",
            "MC_Avatar_Starter"
        };
        var missing = new List<string>();
        foreach (string key in required) if (S(key) == null) missing.Add(key);
        if (missing.Count == 0) return true;
        EditorUtility.DisplayDialog("HealthMon Characters · 스프라이트 누락",
            "설치에 필요한 이미지가 없어 기존 UI를 변경하지 않았습니다.\n\n" +
            string.Join(", ", missing) + "\n\n" +
            "ZIP의 Assets/HealthMon/MultiCharacter/Sprites 폴더를 프로젝트에 병합한 뒤 다시 실행하세요.",
            "확인");
        return false;
    }
    private static TMP_FontAsset EnsureFont()
    {
        var existing=AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(FontPath);
        if(existing!=null)return existing;
        string path="Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold.ttf";
        Font source=AssetDatabase.LoadAssetAtPath<Font>(path);
        if(source==null)
        {
            foreach(string guid in AssetDatabase.FindAssets("t:Font"))
            {
                string p=AssetDatabase.GUIDToAssetPath(guid);
                if(p.IndexOf("Maplestory Bold",StringComparison.OrdinalIgnoreCase)<0)continue;
                source=AssetDatabase.LoadAssetAtPath<Font>(p);if(source!=null)break;
            }
        }
        if(source==null)return null;
        EnsureFolder(Root+"/Fonts");
        var result=TMP_FontAsset.CreateFontAsset(source,90,9,GlyphRenderMode.SDFAA,1024,1024,AtlasPopulationMode.Dynamic,true);
        if(result==null)return null;
        result.name="HealthMon_Roster_KoreanDynamic";
        AssetDatabase.CreateAsset(result,FontPath);
        if(result.material!=null&&!AssetDatabase.Contains(result.material))AssetDatabase.AddObjectToAsset(result.material,result);
        foreach(var atlas in result.atlasTextures)if(atlas!=null&&!AssetDatabase.Contains(atlas))AssetDatabase.AddObjectToAsset(atlas,result);
        AssetDatabase.SaveAssets();return result;
    }
    // Rebuild the roster catalogue from the SAME product IDs used by Shop v3.
    // Never reset purchase records or per-character growth PlayerPrefs.
    private static HealthMonCharacterRosterAsset EnsureCatalog()
    {
        var db=AssetDatabase.LoadAssetAtPath<HealthMonCharacterRosterAsset>(AssetPath);
        if(db==null)
        {
            db=ScriptableObject.CreateInstance<HealthMonCharacterRosterAsset>();
            AssetDatabase.CreateAsset(db,AssetPath);
        }
        if(db.entries==null) db.entries=new List<HealthMonCharacterRosterAsset.Entry>();
        var existing=new Dictionary<string,HealthMonCharacterRosterAsset.Entry>();
        foreach(var e in db.entries)
            if(e!=null&&!string.IsNullOrEmpty(e.id)&&!existing.ContainsKey(e.id)) existing.Add(e.id,e);

        var ordered=new List<HealthMonCharacterRosterAsset.Entry>();
        HealthMonCharacterRosterAsset.Entry starter;
        if(!existing.TryGetValue("pet_starter",out starter)) starter=new HealthMonCharacterRosterAsset.Entry();
        starter.id="pet_starter";
        starter.title=string.IsNullOrEmpty(starter.title)?"헬스몬":starter.title;
        starter.description="처음부터 함께한 헬스몬";
        starter.shopItemId="pet_starter";
        starter.includedByDefault=true;
        if(starter.visualPrefab==null)
            starter.visualPrefab=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/HealthMon/Prefabs/Characters/HealthMon_Slime.prefab");
        if(starter.portrait==null)starter.portrait=S("MC_Avatar_Starter");
        ordered.Add(starter);

        // The shop's exact item IDs are authoritative for local ownership.
        var shop=AssetDatabase.LoadAssetAtPath<HealthMonShopCatalog>("Assets/HealthMon/Shop/HealthMonShopCatalog.asset");
        var prefabs=new SortedDictionary<string,GameObject>(StringComparer.OrdinalIgnoreCase);
        const string prefabDir="Assets/Suriyun/Cute_Slime/Prefab";
        if(AssetDatabase.IsValidFolder(prefabDir))
        {
            foreach(var guid in AssetDatabase.FindAssets("t:Prefab",new[]{prefabDir}))
            {
                string path=AssetDatabase.GUIDToAssetPath(guid);
                var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if(prefab!=null&&prefab.name.StartsWith("Cute_Slime_",StringComparison.OrdinalIgnoreCase))
                    prefabs[prefab.name]=prefab;
            }
        }
        int matched=0,withoutShop=0;
        foreach(var pair in prefabs)
        {
            string suffix=pair.Key.Substring("Cute_Slime_".Length);
            string slotId="slot_"+suffix.ToLowerInvariant();
            string sku="prefab_"+pair.Key.ToLowerInvariant();
            HealthMonShopItem product=null;
            if(shop!=null&&shop.items!=null)
                foreach(var p in shop.items)
                    if(p!=null&&p.category==HealthMonShopCategory.Character&&p.itemId==sku)
                    { product=p; break; }
            if(product!=null)matched++;else withoutShop++;
            HealthMonCharacterRosterAsset.Entry e;
            if(!existing.TryGetValue(slotId,out e))e=new HealthMonCharacterRosterAsset.Entry();
            e.id=slotId;
            e.title=product!=null&&!string.IsNullOrEmpty(product.displayName)?product.displayName:"헬스몬 "+suffix;
            e.description=product!=null&&!string.IsNullOrEmpty(product.description)?product.description:"Cute_Slime_"+suffix+" 캐릭터";
            e.shopItemId=sku;
            e.visualPrefab=pair.Value;
            // Every other character is LOCKED unless its exact shop item ID is in purchase history.
            e.includedByDefault=false;
            string baked= "Assets/HealthMon/Shop/Generated/Icons/"+sku+".png";
            Sprite real=AssetDatabase.LoadAssetAtPath<Sprite>(baked);
            if(real==null&&product!=null&&product.icon!=null)
            {
                string iconPath=AssetDatabase.GetAssetPath(product.icon);
                // Don't substitute a generic cartoon icon for the real prefab photograph.
                if(iconPath.Contains("/Generated/Icons/")||iconPath.Contains("/Portraits/"))real=product.icon;
            }
            if(real==null)real=AssetDatabase.LoadAssetAtPath<Sprite>(Root+"/Portraits/"+slotId+".png");
            if(real!=null)e.portrait=real;
            else if(e.portrait==null)e.portrait=FallbackAvatar(suffix);
            ordered.Add(e);
        }
        // Keep any previously registered prefab entries if the shop has no path yet.
        // Missing prefabs are NOT silently treated as purchasable characters.
        db.entries=ordered;
        EditorUtility.SetDirty(db);
        AssetDatabase.SaveAssets();
        Debug.Log("[Roster] prefab="+prefabs.Count+", shop item ID match="+matched+
                  ", not in shop="+withoutShop+". Only the starter is free; previous purchases are preserved.");
        if(withoutShop>0)
            Debug.LogWarning("[Roster] 상점에 없는 프리팹이 "+withoutShop+
                "개 있습니다. 먼저 Tools > HealthMon > Shop > 7. 오프라인 상점 + 실제 프리팹 등록을 실행하세요.");
        return db;
    }
    private static Sprite FallbackAvatar(string suffix)
    {
        if(suffix.StartsWith("N",StringComparison.OrdinalIgnoreCase))return S("MC_Avatar_Mint");
        if(suffix.StartsWith("O",StringComparison.OrdinalIgnoreCase))return S("MC_Avatar_Lavender");
        if(suffix.StartsWith("P",StringComparison.OrdinalIgnoreCase))return S("MC_Avatar_Blue");
        if(suffix.StartsWith("Q",StringComparison.OrdinalIgnoreCase))return S("MC_Avatar_Pink");
        return S("MC_Avatar_Gold");
    }
    private static RectTransform Rect(string name,Transform parent)
    {var t=new GameObject(name,typeof(RectTransform)).GetComponent<RectTransform>();t.SetParent(parent,false);return t;}
    private static RectTransform Stretch(RectTransform t)
    {t.anchorMin=Vector2.zero;t.anchorMax=Vector2.one;t.pivot=new Vector2(.5f,.5f);t.offsetMin=t.offsetMax=Vector2.zero;return t;}
    private static RectTransform Top(string name,Transform parent,float x,float y,float w,float h)
    {var r=Rect(name,parent);r.anchorMin=r.anchorMax=new Vector2(.5f,1);r.pivot=new Vector2(.5f,.5f);r.anchoredPosition=new Vector2(x,y);r.sizeDelta=new Vector2(w,h);return r;}
    private static RectTransform Bottom(string name,Transform parent,float x,float y,float w,float h)
    {var r=Rect(name,parent);r.anchorMin=r.anchorMax=new Vector2(.5f,0);r.pivot=new Vector2(.5f,.5f);r.anchoredPosition=new Vector2(x,y);r.sizeDelta=new Vector2(w,h);return r;}
    private static RectTransform Center(string name,Transform parent,float x,float y,float w,float h)
    {var r=Rect(name,parent);r.anchorMin=r.anchorMax=new Vector2(.5f,.5f);r.pivot=new Vector2(.5f,.5f);r.anchoredPosition=new Vector2(x,y);r.sizeDelta=new Vector2(w,h);return r;}
    private static Image Pic(RectTransform r, string sprite, Color tint, bool raycast = true)
    {
        var image = r.gameObject.AddComponent<Image>();
        image.sprite = S(sprite);
        image.raycastTarget = raycast;
        bool illustration = sprite.Contains("Avatar") || sprite.Contains("Icon") || sprite.Contains("Backdrop");
        if (image.sprite != null)
        {
            image.type = illustration ? Image.Type.Simple : Image.Type.Sliced;
            image.color = tint;
            image.preserveAspect = sprite.Contains("Avatar") || sprite.Contains("Icon");
        }
        else
        {
            // Prevent the default Image white rectangle from filling the whole screen.
            image.type = Image.Type.Simple;
            image.enabled = !illustration;
            image.color = (sprite == "MC_Backdrop") ? C("#102453") :
                          (sprite == "MC_ConfirmPanel") ? C("#20447E") :
                          (sprite == "MC_Header") ? C("#1A5B98") : C("#254D8C");
        }
        return image;
    }
    private static TMP_Text Text(Transform parent,string name,string value,int size,Color color,TextAlignmentOptions align,float x,float y,float w,float h,int max=0)
    {
        var r=Center(name,parent,x,y,w,h);
        var t=r.gameObject.AddComponent<TextMeshProUGUI>();t.font=font;t.text=value;t.fontSize=size;t.color=color;t.alignment=align;t.raycastTarget=false;
        t.enableWordWrapping=true;t.overflowMode=TextOverflowModes.Ellipsis;t.margin=new Vector4(5,3,5,3);
        if(max>0){t.enableAutoSizing=true;t.fontSizeMin=Mathf.Min(18,size);t.fontSizeMax=max;}
        return t;
    }
    private static Button Btn(Transform parent,string name,string label,string sprite,int size,Color ink,float x,float y,float w,float h)
    {
        var r=Center(name,parent,x,y,w,h);var i=Pic(r,sprite,Color.white);
        var b=r.gameObject.AddComponent<Button>();b.targetGraphic=i;
        var txt=Text(r,"Label",label,size,ink,TextAlignmentOptions.Center,0,0,w-22,h-10);return b;
    }
    // Top-anchored UI helpers: list and header must not drift to the screen centre.
    private static TMP_Text TextTop(Transform parent,string name,string value,int size,Color color,
        TextAlignmentOptions alignment,float x,float y,float w,float h)
    {
        var t=Text(parent,name,value,size,color,alignment,0,0,w,h);
        var rt=(RectTransform)t.transform;
        rt.anchorMin=rt.anchorMax=new Vector2(.5f,1f);
        rt.pivot=new Vector2(.5f,.5f);
        rt.anchoredPosition=new Vector2(x,y);
        return t;
    }
    private static Button ButtonTop(Transform parent,string name,string value,string sprite,int size,Color ink,
        float x,float y,float w,float h)
    {
        var b=Btn(parent,name,value,sprite,size,ink,0,0,w,h);
        var rt=(RectTransform)b.transform;
        rt.anchorMin=rt.anchorMax=new Vector2(.5f,1f);
        rt.pivot=new Vector2(.5f,.5f);
        rt.anchoredPosition=new Vector2(x,y);
        return b;
    }
    private static void BuildRoster(RectTransform root,HealthMonCharacterRosterController c)
    {
        var overlay=Stretch(Rect("CharacterRosterOverlay",root));
        var overlayCanvas=overlay.gameObject.AddComponent<Canvas>();
        overlayCanvas.overrideSorting=true;overlayCanvas.sortingOrder=620;
        overlay.gameObject.AddComponent<GraphicRaycaster>();
        Pic(overlay,"MC_Backdrop",White);
        c.overlay=overlay.gameObject;
        var header=Top("RosterHeader",overlay,0,-100,1000,146);Pic(header,"MC_Header",White);
        Text(header,"HeaderTitle","캐릭터 슬롯",46,White,TextAlignmentOptions.Center,0,0,660,85);
        c.closeButton=Btn(header,"Close","X","MC_ButtonDark",34,White,420,0,95,81);

        // Screen 1: title and filters at the TOP, scroll starts below them.
        var list=Stretch(Rect("SlotListPage",overlay));c.listPage=list.gameObject;
        var banner=Top("RosterSummary",list,0,-255,960,150);Pic(banner,"MC_Panel",White);
        Text(banner,"Intro","나의 헬스몬",38,White,TextAlignmentOptions.Center,0,31,780,60);
        c.bannerText=Text(banner,"RosterCount","구매한 캐릭터를 선택해 육성하세요",26,C("#CCF5F9"),
            TextAlignmentOptions.Center,0,-30,900,65);
        c.allFilterButton=ButtonTop(list,"FilterAll","전체","MC_TabActive",27,C("#0D3D59"),-364,-415,220,80);
        c.ownedFilterButton=ButtonTop(list,"FilterOwned","보유","MC_TabInactive",27,White,-122,-415,220,80);
        c.activeFilterButton=ButtonTop(list,"FilterActive","육성 중","MC_TabInactive",27,White,122,-415,220,80);
        c.lockedFilterButton=ButtonTop(list,"FilterLocked","잠금","MC_TabInactive",27,White,364,-415,220,80);
        c.filterSelectedSprite=S("MC_TabActive");c.filterIdleSprite=S("MC_TabInactive");
        var scrollRect=Rect("SlotScroll",list);
        scrollRect.anchorMin=Vector2.zero;scrollRect.anchorMax=Vector2.one;
        scrollRect.offsetMin=new Vector2(42,185);
        scrollRect.offsetMax=new Vector2(-42,-520);
        var scroll=scrollRect.gameObject.AddComponent<ScrollRect>();
        scroll.horizontal=false;scroll.vertical=true;scroll.scrollSensitivity=38;
        scroll.movementType=ScrollRect.MovementType.Clamped;
        var viewport=Stretch(Rect("Viewport",scrollRect));
        viewport.gameObject.AddComponent<RectMask2D>();scroll.viewport=viewport;
        var content=Rect("Content",viewport);content.anchorMin=new Vector2(0,1);
        content.anchorMax=new Vector2(1,1);content.pivot=new Vector2(.5f,1f);
        content.anchoredPosition=Vector2.zero;content.sizeDelta=new Vector2(0,1400);
        scroll.content=content;c.cardContent=content;
        var template=Top("_CharacterSlotTemplate",content,0,0,455,510);
        var cardBg=Pic(template,"MC_Card",White);
        var button=template.gameObject.AddComponent<Button>();button.targetGraphic=cardBg;
        var port=Top("Portrait",template,0,-174,258,250);
        var portrait=Pic(port,"MC_Avatar_Starter",White,false);portrait.preserveAspect=true;
        var name=TextTop(template,"CharacterName","헬스몬",34,White,TextAlignmentOptions.Center,0,-326,422,54);
        var lev=TextTop(template,"CharacterLevel","Lv. 1",27,C("#FFF2AB"),TextAlignmentOptions.Center,0,-382,422,48);
        var stats=TextTop(template,"CharacterStats","친밀도 45  활동성 32",22,C("#E1F6FF"),TextAlignmentOptions.Center,0,-431,422,52);
        var badge=TextTop(template,"Status","육성 중",24,C("#B9FFF0"),TextAlignmentOptions.Center,0,-479,422,42);
        var card=template.gameObject.AddComponent<HealthMonCharacterSlotCard>();
        card.background=cardBg;card.portrait=portrait;card.nameLabel=name;card.levelLabel=lev;
        card.statsLabel=stats;card.statusLabel=badge;card.button=button;
        card.normalSprite=S("MC_Card");card.activeSprite=S("MC_ActiveCard");card.lockedSprite=S("MC_LockedCard");
        template.gameObject.SetActive(false);c.cardTemplate=card;
        TextTop(list,"FooterHint","미보유 캐릭터는 상점에서 구매하면 해금돼요.",23,
            C("#C9E7FF"),TextAlignmentOptions.Center,0,-1970,925,57);

        // Screen 2: character information and stats (no overlapping footer).
        var detail=Stretch(Rect("CharacterDetailPage",overlay));c.detailPage=detail.gameObject;
        var detailCard=Top("DetailBody",detail,0,-1035,985,1660);Pic(detailCard,"MC_DetailPanel",White);
        c.detailBackButton=ButtonTop(detail,"DetailBack","< 목록","MC_ButtonDark",25,White,-334,-210,290,80);
        c.detailName=TextTop(detail,"PetName","헬스몬",48,White,TextAlignmentOptions.Center,0,-290,785,72);
        var detailPortrait=Top("DetailPortrait",detail,0,-589,445,435);
        c.detailPortrait=Pic(detailPortrait,"MC_Avatar_Starter",White,false);
        c.detailPortrait.preserveAspect=true;
        c.detailLevel=TextTop(detail,"PetLevel","Lv. 1 · 초기형",33,C("#FFEBA9"),TextAlignmentOptions.Center,0,-855,835,65);
        c.detailExp=TextTop(detail,"PetExp","EXP 0 / 100",29,C("#C7FBEF"),TextAlignmentOptions.Center,0,-923,835,60);
        var panel=Top("StatsPanel",detail,0,-1260,905,540);Pic(panel,"MC_StatPanel",White);
        Text(panel,"StatsTitle","성장 상태",34,White,TextAlignmentOptions.Center,0,213,765,62);
        c.detailStats=Text(panel,"StatsText","친밀도\n활동성\n다정함\n호기심",30,White,
            TextAlignmentOptions.Left,0,-22,725,342);
        c.detailOutfit=TextTop(detail,"Outfit","장착 중인 장신구 · 없음",26,C("#DFEEFF"),
            TextAlignmentOptions.Center,0,-1567,875,58);
        c.detailTip=TextTop(detail,"Hint","캐릭터마다 성장 기록이 따로 저장돼요.",25,
            C("#B8F7EF"),TextAlignmentOptions.Center,0,-1660,860,78);
        c.switchButton=Btn(detail,"SwitchCharacter","이 캐릭터로 전환","MC_ButtonGold",32,
            C("#173753"),0,-867,685,102);
        c.switchButtonText=c.switchButton.GetComponentInChildren<TMP_Text>();
        c.backButton=Btn(detail,"BackToSlots","다른 캐릭터 보기","MC_ButtonDark",28,White,0,-974,575,92);
        detail.gameObject.SetActive(false);

        // Screen 3: modal confirmation, explicitly centered and occluding the pages below.
        var confirm=Stretch(Rect("CharacterSwitchConfirm",overlay));c.confirmationPage=confirm.gameObject;
        Pic(confirm,"MC_Backdrop",new Color(.33f,.43f,.68f,.96f));
        var confirmCard=Center("ConfirmCard",confirm,0,0,930,990);Pic(confirmCard,"MC_ConfirmPanel",White);
        Text(confirmCard,"ConfirmTitle","캐릭터 전환",53,White,TextAlignmentOptions.Center,0,369,790,90);
        c.confirmBeforePortrait=Pic(Center("BeforeIcon",confirmCard,-207,112,280,280),"MC_Avatar_Starter",White,false);
        c.confirmAfterPortrait=Pic(Center("AfterIcon",confirmCard,207,112,280,280),"MC_Avatar_Mint",White,false);
        c.confirmBeforePortrait.preserveAspect=true;c.confirmAfterPortrait.preserveAspect=true;
        Text(confirmCard,"Arrow",">",64,C("#A5F8EC"),TextAlignmentOptions.Center,0,122,95,100);
        Text(confirmCard,"BeforeLabel","현재 캐릭터",27,White,TextAlignmentOptions.Center,-210,-70,320,50);
        Text(confirmCard,"AfterLabel","전환 후",27,White,TextAlignmentOptions.Center,210,-70,320,50);
        c.confirmationText=Text(confirmCard,"ConfirmMessage","캐릭터를 전환할까요?",29,C("#E5F7FF"),
            TextAlignmentOptions.Center,0,-185,780,192);
        c.cancelSwitchButton=Btn(confirmCard,"CancelSwitch","취소","MC_ButtonBlue",32,White,-210,-364,355,100);
        c.confirmSwitchButton=Btn(confirmCard,"ConfirmSwitch","전환 완료","MC_ButtonGold",32,C("#183B5D"),210,-364,355,100);
        confirm.gameObject.SetActive(false);overlay.gameObject.SetActive(false);
    }
    // Position the quick switcher directly above the CURRENT BottomNavV2, not at a hardcoded mid-screen offset.
    private static void BuildQuickBar(Transform home, HealthMonCharacterRosterController controller)
    {
        var homeRect = home as RectTransform;
        float navTopY = 265f; // fallback in canvas units
        var nav = FindByName("BottomNavV2") as RectTransform;
        if (nav == null) nav = FindByName("BottomNav") as RectTransform;
        if (nav != null && homeRect != null)
        {
            Canvas.ForceUpdateCanvases();
            Vector3[] corners = new Vector3[4];
            nav.GetWorldCorners(corners);
            // Corners[1] is the top-left; convert its Y into HomePanel's bottom-anchored coordinates.
            float measured = homeRect.InverseTransformPoint(corners[1]).y
                             + homeRect.rect.height * homeRect.pivot.y;
            if (measured > 100f && measured < 750f) navTopY = measured;
        }

        const float barHeight = 104f;
        float centerY = Mathf.Clamp(navTopY + barHeight * .5f + 12f, 220f, 625f);
        var bar = Bottom("HM_CharacterQuickBar", home, 0, centerY, 935, barHeight);
        Pic(bar, "MC_QuickBar", White);
        bar.SetAsLastSibling();
        controller.quickBar = bar.gameObject;

        controller.quickOpenButton = Btn(bar, "OpenCharacterSlots", "캐릭터 슬롯",
            "MC_ButtonGold", 26, C("#153750"), -335, 0, 230, 78);

        controller.quickButtons = new Button[3];
        controller.quickPortraits = new Image[3];
        controller.quickLabels = new TMP_Text[3];
        for (int i = 0; i < 3; i++)
        {
            float x = -100 + i * 152f;
            var button = Btn(bar, "QuickSlot_" + i, "", "MC_SmallChip", 17, White,
                x, 0, 137, 78);
            controller.quickButtons[i] = button;
            var icon = Center("Icon", button.transform, 0, 8, 48, 48);
            controller.quickPortraits[i] = Pic(icon, "MC_Avatar_Starter", White, false);
            controller.quickPortraits[i].preserveAspect = true;
            controller.quickLabels[i] = Text(button.transform, "Name", "", 15, White,
                TextAlignmentOptions.Center, 0, -26, 128, 26);
            button.gameObject.SetActive(i == 0);
        }
        controller.quickActiveSprite = S("MC_TabActive");
        controller.quickIdleSprite = S("MC_SmallChip");

        // The previous home speech bubble is low on the screen; gently lift it only if it overlaps the switcher.
        var speech = home.Find("SpeechBubble") as RectTransform;
        if (speech != null && homeRect != null)
        {
            Canvas.ForceUpdateCanvases();
            Vector3[] corners = new Vector3[4];
            speech.GetWorldCorners(corners);
            float speechBottom = homeRect.InverseTransformPoint(corners[0]).y
                                 + homeRect.rect.height * homeRect.pivot.y;
            float barTop = centerY + barHeight / 2f;
            float overlap = barTop + 16f - speechBottom;
            if (overlap > 0f && overlap < 250f)
            {
                speech.anchoredPosition += new Vector2(0f, overlap);
                Debug.Log("[HealthMon Roster] SpeechBubble lifted by " + overlap.ToString("F0") + " units to avoid overlap.");
            }
        }
        Debug.Log("[HealthMon Roster] QuickBar placed above BottomNav. BottomNav top="
                  + navTopY.ToString("F0") + ", bar center=" + centerY.ToString("F0"));
    }

}
#endif
