#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using UnityEngine.TextCore.LowLevel;

/// <summary>
/// Two-stage installation. No scene edits before a successful asset backup.
/// Source patches stop if the user has changed the expected existing code.
/// </summary>
public static class HealthMonGameRulesInstaller
{
    private const string Root = "Assets/HealthMon/GameFlow";
    private const string PetPath = "Assets/HealthMon/Scripts/State/PetStateManager.cs";
    private const string QuestPath = "Assets/HealthMon/Scripts/Quest/QuestPrototype.cs";
    private const string OfflinePath = "Assets/HealthMon/OfflinePlay/Runtime/HealthMonOfflineGame.cs";
    private const string ServerPath = "Assets/HealthMon/Scripts/API/CommonServerConnection.cs";
    private static TMP_FontAsset font;
    private static Color ColorHex(string hex) { ColorUtility.TryParseHtmlString(hex,out var c);return c; }
    private static readonly Color Pale = new Color(.84f,.95f,1f), White = Color.white;

    [MenuItem("Tools/HealthMon/Game Flow/1. 규칙 코드 백업 및 통합 적용")]
    public static void InstallSourceRules()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode) { Popup("Play 모드 종료 후 실행하세요.");return; }
        try
        {
            if (!File.Exists(PetPath) || !File.Exists(OfflinePath) || !File.Exists(QuestPath) || !File.Exists(ServerPath))
            { Popup("필수 소스가 없습니다. Offline Play v1 설치 여부와 프로젝트 경로를 확인해 주세요."); return; }
            string pet = File.ReadAllText(PetPath);
            string quest = File.ReadAllText(QuestPath);
            string offline = File.ReadAllText(OfflinePath);
            string server = File.ReadAllText(ServerPath);
            // Verify all expected locations BEFORE writing to any original source file.
            string changedPet = PatchPet(pet.Replace("\r\n", "\n"));
            string changedOffline = PatchOffline(offline.Replace("\r\n", "\n"));
            string changedQuest = quest.Replace("private const int MockStartingSteps = 1200;", "private const int MockStartingSteps = 0;");
            string oldFlag = "LocalDemoEnabled = System.Environment.GetEnvironmentVariable(\"HEALTHMON_LOCAL_DEMO\") == \"1\";";
            string newFlag = "LocalDemoEnabled = System.Environment.GetEnvironmentVariable(\"HEALTHMON_LOCAL_DEMO\") == \"1\" || PlayerPrefs.GetInt(\"HealthMon_Offline_Mode_v1\", 1) == 1;";
            string changedServer = server.Contains(newFlag) ? server : server.Contains(oldFlag) ? server.Replace(oldFlag, newFlag)
                : throw new InvalidOperationException("CommonServerConnection에서 오프라인 모드 선언부를 찾을 수 없습니다. 기존 코드를 확인해야 합니다.");
            BackupIfChanged(PetPath, pet, changedPet); BackupIfChanged(OfflinePath, offline, changedOffline);
            BackupIfChanged(QuestPath,quest,changedQuest); BackupIfChanged(ServerPath,server,changedServer);
            PlayerPrefs.SetInt("HealthMon_Offline_Mode_v1", 1); PlayerPrefs.Save();
            AssetDatabase.Refresh();
            Popup("통합 규칙 코드가 적용됐습니다. 컴파일 완료 후 2번 씬/관리자 UI 설치를 실행하세요. 원본은 GameFlow/Backups/Code에 백업됐습니다.");
        }
        catch (Exception e)
        { Debug.LogException(e); Popup("변경을 중단했습니다: " + e.Message + "\n현재 프로젝트 소스에 맞춘 검토가 필요합니다."); }
    }
    private static string PatchPet(string src)
    {
        if (src.Contains("// HM-GAMEFLOW-EXP-v1")) return src;
        string oldLoop = "while (currentExp >= expToNextLevel)";
        if (!src.Contains(oldLoop) || !src.Contains("            level++;") ||
            !src.Contains("expToNextLevel = Mathf.Max(1, data.expToNextLevel);") ||
            !src.Contains("level = Mathf.Max(1, newLevel);"))
            throw new InvalidOperationException("PetStateManager.AddExp 구조가 다릅니다. 덮어쓰기를 중단했습니다.");
        src = src.Replace(oldLoop, "while (level < 50 && currentExp >= expToNextLevel)");
        int begin=src.IndexOf("public void AddExp(int amount)",StringComparison.Ordinal);
        int end=src.IndexOf("public void AddIntimacy",begin,StringComparison.Ordinal);
        if (begin<0||end<begin)throw new InvalidOperationException("AddExp 범위를 찾지 못했습니다.");
        string part=src.Substring(begin,end-begin);
        part=part.Replace("            level++;", "            level++;\n            // HM-GAMEFLOW-EXP-v1\n            expToNextLevel = 100 + 10 * (level - 1);");
        part=part.Replace("        RefreshAllUI();", "        if (level >= 50) { currentExp = 0; expToNextLevel = 580; }\n        RefreshAllUI();");
        src=src.Substring(0,begin)+part+src.Substring(end);
        src=src.Replace("expToNextLevel = Mathf.Max(1, data.expToNextLevel);", "expToNextLevel = 100 + 10 * (level - 1);");
        src=src.Replace("level = Mathf.Max(1, newLevel);", "level = Mathf.Clamp(newLevel, 1, 50);\n        expToNextLevel = 100 + 10 * (level - 1);");
        return src;
    }
    private static string PatchOffline(string src)
    {
        if (src.Contains("// HM-GAMEFLOW-ACTIONS-v1")) return src;
        string[][] rules = {
            new[]{"        pet.AddKindness(1);\n        pet.AddExp(3);", "        pet.AddExp(3);\n        // HM-GAMEFLOW-ACTIONS-v1\n        HealthMonGameRules.Instance?.RecordCare();"},
            new[]{"        pet.AddKindness(1);\n        SaveDaily();", "        HealthMonGameRules.Instance?.RecordMeal(type);\n        SaveDaily();"},
            new[]{"        pet.AddIntimacy(2); pet.AddCuriosity(1); pet.AddExp(5);", "        pet.AddIntimacy(2); pet.AddExp(5);\n        HealthMonGameRules.Instance?.RecordChat(message);"},
            new[]{"        pet.AddActivity(Mathf.Clamp(steps / 500, 1, 8));", "        HealthMonGameRules.Instance?.RecordSteps(steps);"}
        };
        foreach (var pair in rules)
        {
            if (!src.Contains(pair[0])) throw new InvalidOperationException("HealthMonOfflineGame 기존 행동 코드를 찾지 못했어요: " + pair[0].Trim());
            src = src.Replace(pair[0],pair[1]);
        }
        const string start = "        // Growing up offline advances the saved growth stage, but does not invent an AI-made 3D model.";
        const string until = "        var q = ReadQuest();";
        int a=src.IndexOf(start,StringComparison.Ordinal);
        int b=src.IndexOf(until,a<0?0:a,StringComparison.Ordinal);
        if (a<0||b<a)throw new InvalidOperationException("자동 진화 블록을 찾지 못했습니다. 이전과 다른 OfflineGame 버전입니다.");
        src=src.Substring(0,a)+"        // Evolution eligibility is now evaluated by the unified GameRules, not automatically applied.\n"+src.Substring(b);
        return src;
    }
    private static void BackupIfChanged(string path,string oldText,string newText)
    {
        if (oldText == newText) return;
        string backupDir=Root+"/Backups/Code"; Directory.CreateDirectory(backupDir);
        string dest=backupDir+"/"+Path.GetFileName(path)+"."+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".txt";
        File.WriteAllText(dest,oldText,new UTF8Encoding(false));
        File.WriteAllText(path,newText,new UTF8Encoding(false));
        Debug.Log("[GameFlow] Code backed up: "+dest);
    }
    [MenuItem("Tools/HealthMon/Game Flow/2. 씬 백업 + 성장 대시보드/관리자 초기화 설치")]
    public static void InstallScene()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode) { Popup("Play 모드 종료 후 실행하세요.");return; }
        var canvas=UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include,FindObjectsSortMode.None)
            .FirstOrDefault(c=>c.transform.Find("HomePanel")!=null && c.transform.Find("AdminPanel")!=null);
        if (canvas == null) { Popup("MainARScene의 UI/Canvas 아래 HomePanel과 AdminPanel을 찾지 못했습니다."); return; }
        var state=UnityEngine.Object.FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        if (state==null) { Popup("PetStateManager가 없습니다. 설치 중단.");return; }
        font=FindFont();
        if (font==null){Popup("Dynamic TMP 한글 글꼴을 찾지 못했습니다. Fonts 폴더에 한글 TMP 폰트가 필요합니다.");return;}
        if (!BackupScene()) return;
        var existing=canvas.transform.Find("HM_GameFlowSystem");
        if (existing!=null) UnityEngine.Object.DestroyImmediate(existing.gameObject);
        var oldButton=canvas.transform.Find("HomePanel/HM_ShowGrowthRules");
        if (oldButton!=null)UnityEngine.Object.DestroyImmediate(oldButton.gameObject);
        var oldAdmin=canvas.transform.Find("HM_GameFlowSystem/HM_ResetOfflineRules");
        if (oldAdmin!=null)UnityEngine.Object.DestroyImmediate(oldAdmin.gameObject);
        var sys=Rect("HM_GameFlowSystem",canvas.transform); Stretch(sys);
        var rules=sys.gameObject.AddComponent<HealthMonGameRules>();rules.pet=state;
        rules.roster=UnityEngine.Object.FindFirstObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
        var ui=sys.gameObject.AddComponent<HealthMonRulesDashboard>();ui.rules=rules;
        BuildDashboard(sys,ui);
        BuildHomeButton(canvas.transform.Find("HomePanel"),ui);
        BuildAdminTools(canvas.transform.Find("AdminPanel"),sys,ui);
        // UI overlay needs to render above panels and below administrator only when opened.
        sys.SetAsLastSibling();
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        EditorSceneManager.SaveOpenScenes();
        Selection.activeGameObject=sys.gameObject;
        Popup("완료! 홈의 '성장 기록'에서 일일 정산·7일 성격 평가·진화 조건을 볼 수 있습니다. 관리자 패널 하단의 '전체 초기화'로 재실험할 수 있습니다.");
    }
    [MenuItem("Tools/HealthMon/Game Flow/3. 백업 폴더 열기")]
    public static void ShowBackups(){Directory.CreateDirectory(Root+"/Backups");EditorUtility.RevealInFinder(Path.GetFullPath(Root+"/Backups"));}
    [MenuItem("Tools/HealthMon/Game Flow/4. 숫자 규칙 셀프 테스트")]
    public static void TestRules()
    {
        var tests = new[] {
            new { actual=0, target=6000, expected=0 },
            new { actual=1800, target=6000, expected=-2 },
            new { actual=3000, target=6000, expected=-1 },
            new { actual=5100, target=6000, expected=1 },
            new { actual=6000, target=6000, expected=2 },
            new { actual=7200, target=6000, expected=3 }
        };
        int passed=0;
        foreach (var t in tests)
        {
            int got=HealthMonGameRules.CalculateDailyDelta(t.actual,t.target);
            if (got!=t.expected) Debug.LogError("[GameFlow TEST] "+t.actual+" expected "+t.expected+", got "+got);
            else passed++;
        }
        Debug.Log("[GameFlow TEST] daily stat calculations: "+passed+" / "+tests.Length);
        Popup(passed == tests.Length ? "생활 스탯 수치 테스트 통과 (6/6)" : "생활 스탯 수치 테스트 실패. Console을 확인하세요.");
    }
    private static TMP_FontAsset FindFont()
    {
        string[] paths={"Assets/HealthMon/MultiCharacter/Fonts/HealthMon_Roster_KoreanDynamic.asset",
            "Assets/HealthMon/Shop/Fonts/HealthMon_Shop_KoreanDynamic.asset"};
        foreach (var path in paths){var f=AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(path);if(f!=null)return f;}
        foreach(var id in AssetDatabase.FindAssets("t:TMP_FontAsset"))
        {var p=AssetDatabase.GUIDToAssetPath(id);if(p.IndexOf("Korean",StringComparison.OrdinalIgnoreCase)>=0)
         {var f=AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(p);if(f!=null)return f;}}
        // Build our own dynamic Korean atlas from the project's existing TTF.
        const string fontOutput = Root + "/HealthMon_Rules_KoreanDynamic.asset";
        var saved = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(fontOutput);
        if (saved != null) return saved;
        var source = AssetDatabase.LoadAssetAtPath<Font>("Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold.ttf");
        if (source == null) return null;
        var result = TMP_FontAsset.CreateFontAsset(source, 90, 9, GlyphRenderMode.SDFAA,
            1024, 1024, AtlasPopulationMode.Dynamic, true);
        if (result == null) return null;
        result.name = "HealthMon_Rules_KoreanDynamic";
        AssetDatabase.CreateAsset(result, fontOutput);
        if (result.material != null && !AssetDatabase.Contains(result.material))
            AssetDatabase.AddObjectToAsset(result.material, result);
        foreach (var atlas in result.atlasTextures)
            if (atlas != null && !AssetDatabase.Contains(atlas)) AssetDatabase.AddObjectToAsset(atlas, result);
        AssetDatabase.SaveAssets();
        return result;
    }
    private static bool BackupScene()
    {
        var s=SceneManager.GetActiveScene();
        if(!s.IsValid()||string.IsNullOrEmpty(s.path)){Popup("먼저 MainARScene을 저장해 주세요.");return false;}
        EditorSceneManager.SaveScene(s);
        string folder=Root+"/Backups/Scenes";if(!AssetDatabase.IsValidFolder(Root+"/Backups"))AssetDatabase.CreateFolder(Root,"Backups");
        if(!AssetDatabase.IsValidFolder(folder))AssetDatabase.CreateFolder(Root+"/Backups","Scenes");
        string path=folder+"/"+Path.GetFileNameWithoutExtension(s.path)+"_BeforeRules_"+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".unity";
        if(!AssetDatabase.CopyAsset(s.path,path)){Popup("씬 백업이 실패했습니다. 설치 중단.");return false;}
        return true;
    }
    private static RectTransform Rect(string name,Transform parent)
    {var go=new GameObject(name,typeof(RectTransform));go.transform.SetParent(parent,false);return go.GetComponent<RectTransform>();}
    private static void Stretch(RectTransform rect)
    {rect.anchorMin=Vector2.zero;rect.anchorMax=Vector2.one;rect.offsetMin=rect.offsetMax=Vector2.zero;rect.pivot=new Vector2(.5f,.5f);}
    private static RectTransform Center(string name,Transform p,float x,float y,float w,float h)
    {var r=Rect(name,p);r.anchorMin=r.anchorMax=new Vector2(.5f,.5f);r.sizeDelta=new Vector2(w,h);r.anchoredPosition=new Vector2(x,y);return r;}
    private static RectTransform Top(string name,Transform p,float x,float y,float w,float h)
    {var r=Rect(name,p);r.anchorMin=r.anchorMax=new Vector2(.5f,1);r.sizeDelta=new Vector2(w,h);r.anchoredPosition=new Vector2(x,y);return r;}
    private static void Background(RectTransform r,Color c)
    {var i=r.gameObject.AddComponent<Image>();i.color=c;i.raycastTarget=true;}
    private static TMP_Text Text(Transform p,string name,string value,int size,float x,float y,float w,float h,Color col)
    {var r=Center(name,p,x,y,w,h);var t=r.gameObject.AddComponent<TextMeshProUGUI>();t.font=font;t.fontSize=size;t.color=col;t.text=value;
     t.alignment=TextAlignmentOptions.Center;t.enableWordWrapping=true;t.overflowMode=TextOverflowModes.Ellipsis;t.raycastTarget=false;return t;}
    private static Button Button(Transform p,string name,string caption,float x,float y,float w,float h,Color bg,Color ink)
    {var r=Center(name,p,x,y,w,h);Background(r,bg);var b=r.gameObject.AddComponent<Button>();b.targetGraphic=r.GetComponent<Image>();
     Text(r,"Label",caption,27,0,0,w-12,h-8,ink);return b;}
    private static TMP_InputField Input(Transform parent,string name,string hint,float x,float y,float w,float h)
    {
        var r=Center(name,parent,x,y,w,h);Background(r,ColorHex("#E5F4FF"));
        var input=r.gameObject.AddComponent<TMP_InputField>();input.contentType=TMP_InputField.ContentType.IntegerNumber;
        var viewport=Rect("Text Area",r);Stretch(viewport);viewport.offsetMin=new Vector2(14,4);viewport.offsetMax=new Vector2(-14,-4);
        viewport.gameObject.AddComponent<RectMask2D>();
        var txt=Text(viewport,"Text","",26,0,0,w-50,h-10,ColorHex("#0B2448"));
        var placeholder=Text(viewport,"Placeholder",hint,21,0,0,w-50,h-10,ColorHex("#647F9D"));
        input.textViewport=viewport;input.textComponent=(TextMeshProUGUI)txt;input.placeholder=(Graphic)placeholder;
        return input;
    }
    private static void BuildDashboard(RectTransform sys,HealthMonRulesDashboard ui)
    {
        var overlay=Rect("RulesDashboardOverlay",sys);Stretch(overlay);Background(overlay,ColorHex("#091831"));
        var canvas=overlay.gameObject.AddComponent<Canvas>();canvas.overrideSorting=true;canvas.sortingOrder=810;
        overlay.gameObject.AddComponent<GraphicRaycaster>();ui.rulesOverlay=overlay.gameObject;
        var title=Top("Header",overlay,0,-102,978,124);Background(title,ColorHex("#154581"));
        Text(title,"Title","성장 · 게임 규칙",45,-65,0,690,90,White);
        ui.closeButton=Button(title,"Close","×",428,0,92,82,ColorHex("#2369AF"),White);
        var panel=Center("SummaryCard",overlay,0,400,985,595);Background(panel,ColorHex("#153B73"));
        ui.summary=Text(panel,"Summary","실제 성장 데이터를 불러옵니다.",26,0,0,912,532,Pale);
        ui.summary.alignment=TextAlignmentOptions.TopLeft;
        Text(overlay,"ManualTitle","추가 운동 기록 (직접 입력)",33,0,10,950,58,White);
        ui.upperInput=Input(overlay,"UpperInput","상체 운동 횟수",-220,-85,510,94);
        ui.upperButton=Button(overlay,"UpperSave","기록",280,-85,245,94,ColorHex("#52D5CB"),ColorHex("#102B53"));
        ui.cardioInput=Input(overlay,"CardioInput","유산소 운동 분",-220,-207,510,94);
        ui.cardioButton=Button(overlay,"CardioSave","기록",280,-207,245,94,ColorHex("#52D5CB"),ColorHex("#102B53"));
        ui.evolutionButton=Button(overlay,"EvolveStage","조건 충족 시 진화 단계 적용",0,-373,860,107,ColorHex("#EFCB69"),ColorHex("#132D51"));
        ui.note=Text(overlay,"Notice","걷기·식사는 기존 패널에서 기록하세요. 운동 입력은 센서 측정값이 아닙니다.",22,0,-510,945,100,Pale);
        Text(overlay,"RulesFooter","하루 정산: 기록된 날짜만 적용 · 성격: 7일마다 평가 · 코인: 공용 · EXP: 캐릭터별",19,0,-710,980,92,Pale);
        overlay.gameObject.SetActive(false);
    }
    private static void BuildHomeButton(Transform home,HealthMonRulesDashboard ui)
    {
        var r=Rect("HM_ShowGrowthRules",home);r.anchorMin=r.anchorMax=new Vector2(1f,1f);r.pivot=new Vector2(1f,1f);
        r.sizeDelta=new Vector2(265,77);r.anchoredPosition=new Vector2(-22,-245);
        Background(r,ColorHex("#194B83"));var b=r.gameObject.AddComponent<Button>();b.targetGraphic=r.GetComponent<Image>();
        Text(r,"Label","성장 기록",25,0,0,248,70,White);ui.openButton=b;
    }
    private static void BuildAdminTools(Transform admin,RectTransform sys,HealthMonRulesDashboard ui)
    {
        // MobileAdminMenu.Configure() deactivates every pre-existing AdminPanel child.
        // Put our launcher in a separate sorting canvas and show it ONLY while AdminPanel is visible.
        var root=Rect("HM_ResetOfflineRules",sys);root.anchorMin=root.anchorMax=new Vector2(.5f,0);
        root.sizeDelta=new Vector2(920,155);root.anchoredPosition=new Vector2(0,200);
        var ownCanvas=root.gameObject.AddComponent<Canvas>();ownCanvas.overrideSorting=true;ownCanvas.sortingOrder=820;
        root.gameObject.AddComponent<GraphicRaycaster>();
        Background(root,ColorHex("#183F70"));
        ui.adminPanel=admin.gameObject;ui.adminLauncher=root.gameObject;
        root.gameObject.SetActive(false);
        ui.resetOpenButton=Button(root,"OpenReset","오프라인 실험 전체 초기화",0,24,730,73,ColorHex("#BC4960"),White);
        ui.adminFeedback=Text(root,"AdminNote","게임 저장값만 초기화 · 서버 데이터는 유지",20,0,-50,825,42,Pale);
        var modal=Rect("ConfirmLocalReset",sys);Stretch(modal);Background(modal,new Color(.03f,.06f,.13f,.95f));
        var c=modal.gameObject.AddComponent<Canvas>();c.overrideSorting=true;c.sortingOrder=999;
        modal.gameObject.AddComponent<GraphicRaycaster>();
        var card=Center("ResetCard",modal,0,0,940,660);Background(card,ColorHex("#14376B"));
        Text(card,"Title","전체 초기화 · 되돌릴 수 없음",40,0,235,860,83,White);
        Text(card,"Warn","닉네임·모든 캐릭터 성장·퀘스트·로컬 코인·구매·장착 기록을 삭제합니다.\n서버 데이터는 삭제하지 않습니다. 확인하려면 '초기화'라고 입력하세요.",28,0,97,810,190,Pale);
        ui.resetPhrase=Input(card,"Phrase","초기화",0,-52,740,87);
        ui.resetPhrase.contentType=TMP_InputField.ContentType.Standard;
        ui.resetCancelButton=Button(card,"Cancel","취소",-222,-214,315,91,ColorHex("#2474A8"),White);
        ui.resetConfirmButton=Button(card,"Confirm","모든 로컬 데이터 삭제",222,-214,360,91,ColorHex("#BB3B5B"),White);
        ui.resetConfirm=modal.gameObject;modal.gameObject.SetActive(false);
    }
    private static void Popup(string message) => EditorUtility.DisplayDialog("HealthMon · Game Flow",message,"확인");
}
#endif
