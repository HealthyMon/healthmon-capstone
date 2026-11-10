#if UNITY_EDITOR
using System;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine.Events;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public static class HealthMonOfflineInstaller
{
    private const string Root = "Assets/HealthMon/OfflinePlay";
    private const string ServerCode = "Assets/HealthMon/Scripts/API/CommonServerConnection.cs";
    private const string QuestCode = "Assets/HealthMon/Scripts/Quest/QuestPrototype.cs";
    private const string ModeKey = HealthMonOfflineGame.ModeKey;
    private static TMP_FontAsset font;
    private static readonly Color Ink = Hex("#FFFFFF"), Muted = Hex("#B5D7ED"), Navy = Hex("#0C2349");

    [MenuItem("Tools/HealthMon/Offline Play/1. 오프라인 모드 활성화 (코드 백업 및 컴파일)")]
    public static void EnableOffline()
    {
        if (EditorApplication.isPlaying) { EditorUtility.DisplayDialog("Offline Play", "Play 모드를 종료해 주세요.", "확인"); return; }
        if (!File.Exists(ServerCode)) { EditorUtility.DisplayDialog("Offline Play", "CommonServerConnection.cs를 찾지 못했습니다. 프로젝트 경로를 확인해 주세요.", "확인"); return; }
        string text = File.ReadAllText(ServerCode);
        string old = "LocalDemoEnabled = System.Environment.GetEnvironmentVariable(\"HEALTHMON_LOCAL_DEMO\") == \"1\";";
        string replacement = "LocalDemoEnabled = System.Environment.GetEnvironmentVariable(\"HEALTHMON_LOCAL_DEMO\") == \"1\" || PlayerPrefs.GetInt(\"HealthMon_Offline_Mode_v1\", 1) == 1;";
        if (!text.Contains(replacement))
        {
            if (!text.Contains(old))
            { EditorUtility.DisplayDialog("Offline Play", "서버 연결 스크립트가 이전 프로젝트 버전과 달라 자동 변경을 중단했습니다. 원본 스크립트를 보내주세요.", "확인"); return; }
            EnsureFolder(Root + "/Backups");
            BackupFile(ServerCode);
            File.WriteAllText(ServerCode, text.Replace(old, replacement), System.Text.Encoding.UTF8);
        }
        if (File.Exists(QuestCode))
        {
            string q = File.ReadAllText(QuestCode);
            if (q.Contains("private const int MockStartingSteps = 1200;"))
            {
                BackupFile(QuestCode);
                File.WriteAllText(QuestCode, q.Replace("private const int MockStartingSteps = 1200;", "private const int MockStartingSteps = 0;"), System.Text.Encoding.UTF8);
            }
        }
        PlayerPrefs.SetInt(ModeKey, 1); PlayerPrefs.Save();
        AssetDatabase.Refresh();
        EditorUtility.DisplayDialog("Offline Play", "오프라인 모드를 기본값으로 활성화했습니다. 컴파일이 끝나면 2번 UI 설치 메뉴를 실행하세요. 기존 코드 백업은 OfflinePlay/Backups에 저장됐습니다.", "확인");
    }

    [MenuItem("Tools/HealthMon/Offline Play/2. 메인 씬 백업 + 오프라인 육성 UI 설치")]
    public static void Install()
    {
        if (EditorApplication.isPlaying) { EditorUtility.DisplayDialog("Offline Play", "Play 모드를 종료해 주세요.", "확인"); return; }
        Canvas canvas = FindMainCanvas();
        if (canvas == null) { EditorUtility.DisplayDialog("Offline Play", "MainARScene의 UI → Canvas → HomePanel을 찾지 못했어요.", "확인"); return; }
        if (!File.Exists(ServerCode) || !File.ReadAllText(ServerCode).Contains("HealthMon_Offline_Mode_v1"))
        { EditorUtility.DisplayDialog("Offline Play", "먼저 1번 오프라인 모드 활성화 메뉴를 실행하세요.", "확인"); return; }
        if (!BackupScene()) return;
        ImportSprites();
        font = EnsureKoreanFont();
        if (font == null) { EditorUtility.DisplayDialog("Offline Play", "Maplestory Bold.ttf 글꼴을 찾지 못했습니다. 폰트 오류를 해결한 뒤 진행하세요.", "확인"); return; }
        Transform existing = canvas.transform.Find("HM_OfflineGameplay");
        if (existing != null) UnityEngine.Object.DestroyImmediate(existing.gameObject);
        var root = NewRect("HM_OfflineGameplay", canvas.transform);
        var game = root.gameObject.AddComponent<HealthMonOfflineGame>();
        game.pet = UnityEngine.Object.FindFirstObjectByType<PetStateManager>(FindObjectsInactive.Include);
        game.quests = UnityEngine.Object.FindFirstObjectByType<QuestPrototype>(FindObjectsInactive.Include);
        game.serverDialogue = UnityEngine.Object.FindFirstObjectByType<DialoguePrototype>(FindObjectsInactive.Include);
        var home = canvas.transform.Find("HomePanel");
        var quest = canvas.transform.Find("QuestPanel");
        var food = canvas.transform.Find("FoodScanPanel");
        var dialog = canvas.transform.Find("DialoguePanel");
        var wearable = canvas.transform.Find("WearablePanel");
        if (home == null || quest == null || food == null || dialog == null || wearable == null)
        {
            UnityEngine.Object.DestroyImmediate(root.gameObject);
            EditorUtility.DisplayDialog("Offline Play", "필수 패널을 찾지 못했습니다. 기존 MainARScene을 열어주세요.", "확인"); return;
        }
        game.homePanel = home.gameObject; game.questPanel = quest.gameObject;
        game.foodPanel = food.gameObject; game.dialoguePanel = dialog.gameObject;
        game.wearablePanel = wearable.gameObject;
        BuildHome(home, game);
        BuildQuest(quest, game);
        BuildFood(food, game);
        BuildDialogue(dialog, game);
        BuildWorkout(wearable, game);
        ApplyKoreanFont(canvas.transform);
        EditorUtility.SetDirty(game);
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        EditorSceneManager.SaveOpenScenes();
        Selection.activeGameObject = root.gameObject;
        EditorUtility.DisplayDialog("Offline Play", "오프라인 육성 UI 설치 완료! Play 후 홈→교감, 퀘스트, 음식, 대화, 웨어러블에서 직접 기록하고 보상을 받아보세요. 오프라인 상점 v3가 있다면 같은 코인 잔액을 사용합니다.", "확인");
    }

    [MenuItem("Tools/HealthMon/Offline Play/3. 서버 모드로 전환 (다음 Play부터)")]
    public static void ServerMode()
    {
        PlayerPrefs.SetInt(ModeKey, 0); PlayerPrefs.Save();
        EditorUtility.DisplayDialog("Offline Play", "에디터 서버 모드로 변경했습니다. Play를 종료하고 다시 실행하면 적용됩니다. 모바일 기기는 자체 PlayerPrefs를 사용하므로 별도 설정이 필요합니다.", "확인");
    }
    [MenuItem("Tools/HealthMon/Offline Play/4. 오프라인 모드로 전환 (다음 Play부터)")]
    public static void OfflineMode()
    {
        PlayerPrefs.SetInt(ModeKey, 1); PlayerPrefs.Save();
        EditorUtility.DisplayDialog("Offline Play", "에디터 오프라인 모드로 변경했습니다. Play를 다시 시작하면 적용됩니다.", "확인");
    }
    [MenuItem("Tools/HealthMon/Offline Play/5. UI만 제거 (세이브는 유지)")]
    public static void RemoveUI()
    {
        if (EditorApplication.isPlaying) return;
        var canvas = FindMainCanvas(); if (canvas == null) return;
        if (!BackupScene()) return;
        var root = canvas.transform.Find("HM_OfflineGameplay");
        if (root != null) UnityEngine.Object.DestroyImmediate(root.gameObject);
        foreach (string pair in new[] { "HomePanel/HM_OfflineCareButton", "QuestPanel/HM_OfflineQuestSurface",
            "FoodScanPanel/HM_OfflineFoodSurface", "DialoguePanel/HM_OfflineDialogueSurface",
            "WearablePanel/HM_OfflineWorkoutSurface" })
        { var child = canvas.transform.Find(pair); if (child != null) UnityEngine.Object.DestroyImmediate(child.gameObject); }
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        EditorUtility.DisplayDialog("Offline Play", "오프라인 UI만 제거했습니다. 로컬 저장 기록과 서버 모드 패치는 유지됩니다.", "확인");
    }

    private static void BuildHome(Transform home, HealthMonOfflineGame game)
    {
        RemoveOld(home,"HM_OfflineCareButton");
        var btn = Button("HM_OfflineCareButton", home, "♥ 쓰다듬기", "ButtonMint", 245, 78, 27, true);
        var t = (RectTransform)btn.transform; t.anchorMin=t.anchorMax = new Vector2(1,1); t.pivot = new Vector2(1,1);
        t.anchoredPosition = new Vector2(-20, -670);
        UnityEventTools.AddPersistentListener(btn.onClick,game.PetCare); game.homeCareButton = btn.gameObject;
        var label = Label("HM_CareHint",btn.transform,"오프라인 교감",18,Muted,220,26);
        Rect(label).anchoredPosition = new Vector2(0,-53);
        game.homeHint = label;
    }

    private static void BuildQuest(Transform panel, HealthMonOfflineGame game)
    {
        RemoveOld(panel,"HM_OfflineQuestSurface");
        var root = NewRect("HM_OfflineQuestSurface", panel);
        StretchMargins(root,24,205,24,150);
        AddSpriteImage(root,"PanelDark"); game.questSurface = root.gameObject;
        var title = Label("Heading",root,"오늘의 퀘스트",42,Ink,800,70); Top(title,-85);
        game.questSummary = Label("QuestSummary",root,"오늘의 목표 0 / 4",26,Muted,740,55); Top(game.questSummary,-154);
        game.questCards = new HealthMonOfflineGame.OfflineQuestCard[4];
        string[] names={"3,000보 걸음 기록","음식 한 번 기록하기","헬스몬과 대화하기","펫과 3회 교감하기"};
        string[] rewards={"EXP 100 · 코인 30", "EXP 50 · 코인 20", "EXP 50 · 코인 20", "EXP 80 · 코인 25"};
        UnityAction[] actions={game.ClaimWalk,game.ClaimFood,game.ClaimDialogue,game.ClaimAR};
        for(int i=0;i<4;i++)
        {
            var card = NewRect("QuestCard_"+i,root); Top(card,-287-i*260); card.sizeDelta=new Vector2(916,222); AddSpriteImage(card,"PanelLight");
            var heading=Label("QuestName",card,names[i],31,Ink,650,52); Top(heading,-51); Rect(heading).anchoredPosition=new Vector2(-64,-51);
            var reward=Label("Reward",card,rewards[i],22,Muted,600,38); Top(reward,-95); Rect(reward).anchoredPosition=new Vector2(-83,-95);
            var track=NewRect("Track",card); Top(track,-153); track.sizeDelta=new Vector2(520,27); track.anchoredPosition=new Vector2(-150,-153); AddSpriteImage(track,"ProgressTrack");
            var fill=NewRect("Fill",track); Stretch(fill); var fillImage=AddSpriteImage(fill,"ProgressFill"); fillImage.type=Image.Type.Filled; fillImage.fillMethod=Image.FillMethod.Horizontal; fillImage.fillAmount=0;
            var progress=Label("Progress",card,"0 / 1",23,Ink,150,40); Top(progress,-150); Rect(progress).anchoredPosition =new Vector2(215,-153);
            var b=Button("ClaimReward",card,"진행 중","ButtonGold",250,69,25);
            Top((RectTransform)b.transform,-184); ((RectTransform)b.transform).anchoredPosition=new Vector2(284,-174);
            UnityEventTools.AddPersistentListener(b.onClick,actions[i]);
            game.questCards[i] = new HealthMonOfflineGame.OfflineQuestCard { progress=progress,progressFill=fillImage,claimButton=b,claimLabel=b.GetComponentInChildren<TMP_Text>() };
        }
        var foot=Label("QuestFoot",root,"걸음·식사·대화·교감으로 미션을 완료하면 보상을 받을 수 있어요.",23,Muted,850,77); Top(foot,-1402);
    }

    private static void BuildFood(Transform panel, HealthMonOfflineGame game)
    {
        RemoveOld(panel,"HM_OfflineFoodSurface");
        var root = NewRect("HM_OfflineFoodSurface",panel); Bottom(root,0,210,960,405);
        AddSpriteImage(root,"PanelDark"); game.foodSurface=root.gameObject;
        var head=Label("Title",root,"오프라인 식사 기록",34,Ink,860,55);Top(head,-60);
        var sub=Label("Note",root,"AI 분석 없이 식사를 수동으로 기록합니다.",24,Muted,850,42);Top(sub,-111);
        string[] meals={"아침 기록","점심 기록","저녁 기록"};
        UnityAction[] methods={game.RecordBreakfast,game.RecordLunch,game.RecordDinner};
        for(int i=0;i<3;i++)
        {
            var b=Button("Meal_"+i,root,meals[i],i==1?"ButtonGold":"ButtonMint",276,74,27);
            Top((RectTransform)b.transform,-208);((RectTransform)b.transform).anchoredPosition=new Vector2(-304+i*304,-208);
            UnityEventTools.AddPersistentListener(b.onClick,methods[i]);
        }
        game.foodNotice=Label("FoodNotice",root,"기록하면 EXP·코인을 얻고 오늘 퀘스트가 진행돼요.",22,Muted,880,92); Top(game.foodNotice,-319);
    }

    private static void BuildDialogue(Transform panel,HealthMonOfflineGame game)
    {
        RemoveOld(panel,"HM_OfflineDialogueSurface");
        var root=NewRect("HM_OfflineDialogueSurface",panel); Bottom(root,0,206,960,400); AddSpriteImage(root,"PanelDark");game.dialogueSurface=root.gameObject;
        var head=Label("Title",root,"헬스몬과 교감",32,Ink,800,54);Top(head,-45);
        game.dialogueLog=Label("LastUserMessage",root,"내가 한 말이 여기에 표시돼요.",24,Muted,810,43);Top(game.dialogueLog,-105);
        game.dialogueReply=Label("OfflineReply",root,"안녕! 함께 성장하자.",27,Ink,840,96);Top(game.dialogueReply,-177);
        var input=Input("OfflineInput",root,"헬스몬에게 말해 보세요...",700,75,false); Bottom((RectTransform)input.transform,-92,34,700,75); game.dialogueInput=input;
        var send=Button("SendOffline",root,"보내기","ButtonMint",176,75,26);Bottom((RectTransform)send.transform,345,34,176,75);
        UnityEventTools.AddPersistentListener(send.onClick,game.SendOfflineMessage);
        var footer=Label("Disclaimer",root,"오프라인 대화는 준비된 반응이며 LLM 연결을 사용하지 않아요.",17,Muted,880,37);Bottom(Rect(footer),0,5,880,37);
    }

    private static void BuildWorkout(Transform panel,HealthMonOfflineGame game)
    {
        RemoveOld(panel,"HM_OfflineWorkoutSurface");
        var root=NewRect("HM_OfflineWorkoutSurface",panel);StretchMargins(root,22,212,22,145);AddSpriteImage(root,"PanelDark");game.workoutSurface=root.gameObject;
        var title=Label("Title",root,"운동 · 성장 기록",41,Ink,860,65);Top(title,-82);
        var help=Label("Help",root,"웨어러블 없이 걸음 수를 직접 입력해 기록할 수 있어요.",23,Muted,860,74); Top(help,-153);
        game.growthSummary=Label("Growth",root,"현재 성장 상태",27,Ink,862,110);Top(game.growthSummary,-268);
        game.workoutSummary=Label("RecordSummary",root,"오늘 0보",31,Ink,862,68);Top(game.workoutSummary,-398);
        var chart=NewRect("SevenDayGraph",root);Top(chart,-610);chart.sizeDelta=new Vector2(850,300);AddSpriteImage(chart,"PanelLight");
        game.weekBars=new Image[7];
        for (int i=0;i<7;i++)
        {
            var bar=NewRect("Bar_"+i,chart);Bottom(bar,-339+i*112,74,64,170);
            var bg=AddSpriteImage(bar,"ProgressTrack");bg.color=new Color(.12f,.28f,.48f,.9f);
            var fill=NewRect("Fill",bar);Stretch(fill);var image=AddSpriteImage(fill,"ProgressFill");image.type=Image.Type.Filled;
            image.fillMethod=Image.FillMethod.Vertical;image.fillOrigin=0;image.fillAmount=.0f;
            game.weekBars[i]=image;
            var day=Label("Day",chart,DateTime.Now.Date.AddDays(i-6).ToString("M/d"),22,Muted,93,36);
            Bottom(Rect(day),-339+i*112,20,93,36);
        }
        var input=Input("StepsInput",root,"걸음 수 입력 (예: 500)",600,81,true);Top((RectTransform)input.transform,-860);((RectTransform)input.transform).anchoredPosition=new Vector2(-138,-860);game.stepInput=input;
        var send=Button("RecordSteps",root,"기록하기","ButtonGold",220,81,27);Top((RectTransform)send.transform,-860);((RectTransform)send.transform).anchoredPosition=new Vector2(330,-860);
        UnityEventTools.AddPersistentListener(send.onClick,game.RecordSteps);
        game.workoutNotice=Label("RecordNotice",root,"수동 걸음 기록은 실제 센서 측정값이 아닙니다.",21,Muted,850,75);Top(game.workoutNotice,-969);
        game.workoutHistory=Label("History",root,"최근 걸음 기록",23,Ink,840,240);Top(game.workoutHistory,-1205);
    }

    private static bool BackupScene()
    {
        var s=SceneManager.GetActiveScene();
        if (!s.IsValid() || string.IsNullOrWhiteSpace(s.path))
        {EditorUtility.DisplayDialog("Offline Play", "먼저 MainARScene을 저장해 주세요.", "확인"); return false;}
        EditorSceneManager.SaveScene(s);
        EnsureFolder(Root+"/Backups");
        string destination=Root+"/Backups/"+Path.GetFileNameWithoutExtension(s.path)+"_BeforeOffline_"+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".unity";
        if (!AssetDatabase.CopyAsset(s.path,destination)) {EditorUtility.DisplayDialog("Offline Play", "씬 백업 실패. 설치를 중단했어요.", "확인");return false;}
        return true;
    }
    private static void BackupFile(string path)
    {
        EnsureFolder(Root+"/Backups");
        string dst=Root+"/Backups/"+Path.GetFileName(path)+"_BeforeOffline_"+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".txt";
        File.Copy(path,dst,true);
    }
    private static Canvas FindMainCanvas()
    {
        foreach(var c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include,FindObjectsSortMode.None))
            if(c.transform.Find("HomePanel")!=null && c.transform.Find("QuestPanel")!=null) return c;
        return null;
    }
    private static void EnsureFolder(string path)
    {
        string[] parts=path.Split('/');string current=parts[0];
        for(int i=1;i<parts.Length;i++)
        {
            var next=current+"/"+parts[i];
            if(!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(current,parts[i]);
            current=next;
        }
    }
    private static void ImportSprites()
    {
        foreach(string f in Directory.GetFiles(Root+"/Sprites","*.png"))
        {
            string p=f.Replace('\\','/');
            var imp=AssetImporter.GetAtPath(p) as TextureImporter; if(imp==null) continue;
            imp.textureType=TextureImporterType.Sprite;
            imp.alphaIsTransparency=true; imp.spriteBorder=new Vector4(32,32,32,32);
            imp.SaveAndReimport();
        }
    }
    private static TMP_FontAsset EnsureKoreanFont()
    {
        var path=Root+"/Generated/HM_Offline_Korean_Dynamic.asset";
        var previous=AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(path); if(previous!=null)return previous;
        var f=AssetDatabase.LoadAssetAtPath<Font>("Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold.ttf");
        if(f==null)return null;
        EnsureFolder(Root+"/Generated");
        var asset=TMP_FontAsset.CreateFontAsset(f);
        asset.atlasPopulationMode=AtlasPopulationMode.Dynamic;
        asset.isMultiAtlasTexturesEnabled=true;
        AssetDatabase.CreateAsset(asset,path);AssetDatabase.SaveAssets();
        return asset;
    }
    private static void ApplyKoreanFont(Transform canvas)
    {
        foreach(var text in canvas.GetComponentsInChildren<TMP_Text>(true))
            if(text!=null && (text.font==null || text.font.name.Contains("Maplestory") || text.font.name.Contains("MapleStory") || text.font.name.Contains("HM_Offline")))
            { text.font=font;EditorUtility.SetDirty(text); }
    }

    private static Sprite GetSprite(string name) => AssetDatabase.LoadAssetAtPath<Sprite>(Root+"/Sprites/"+name+".png");
    private static Color Hex(string code) { ColorUtility.TryParseHtmlString(code,out Color c);return c; }
    private static RectTransform NewRect(string name,Transform parent)
    {
        var g=new GameObject(name,typeof(RectTransform));g.transform.SetParent(parent,false);return (RectTransform)g.transform;
    }
    private static void RemoveOld(Transform parent,string name) { var x=parent.Find(name); if(x!=null)UnityEngine.Object.DestroyImmediate(x.gameObject); }
    private static void Stretch(RectTransform t)
    {t.anchorMin=Vector2.zero;t.anchorMax=Vector2.one;t.offsetMin=Vector2.zero;t.offsetMax=Vector2.zero;}
    private static void StretchMargins(RectTransform t,float left,float bottom,float right,float top)
    {t.anchorMin=Vector2.zero;t.anchorMax=Vector2.one;t.offsetMin=new Vector2(left,bottom);t.offsetMax=new Vector2(-right,-top);}
    private static void Top(RectTransform t,float y)
    {t.anchorMin=t.anchorMax=new Vector2(.5f,1);t.pivot=new Vector2(.5f,.5f);t.anchoredPosition=new Vector2(0,y);}
    private static void Top(TMP_Text t,float y) => Top(Rect(t),y);
    private static void Bottom(RectTransform t,float x,float y,float w,float h)
    {t.anchorMin=t.anchorMax=new Vector2(.5f,0);t.pivot=new Vector2(.5f,0);t.sizeDelta=new Vector2(w,h);t.anchoredPosition=new Vector2(x,y);}
    private static RectTransform Rect(TMP_Text t)=>(RectTransform)t.transform;
    private static Image AddSpriteImage(RectTransform t,string sprite)
    {var img=t.gameObject.AddComponent<Image>();img.sprite=GetSprite(sprite);img.type=img.sprite!=null?Image.Type.Sliced:Image.Type.Simple;img.color=Color.white;return img;}
    private static TMP_Text Label(string name,Transform parent,string content,int size,Color color,float width,float height)
    {
        var t=NewRect(name,parent);t.anchorMin=t.anchorMax=new Vector2(.5f,.5f);t.sizeDelta=new Vector2(width,height);
        var txt=t.gameObject.AddComponent<TextMeshProUGUI>();txt.font=font;txt.text=content;txt.fontSize=size;
        txt.alignment=TextAlignmentOptions.Center;txt.color=color;txt.raycastTarget=false;txt.enableWordWrapping=true;
        txt.overflowMode=TextOverflowModes.Ellipsis;txt.margin=new Vector4(6,4,6,4);return txt;
    }
    private static Button Button(string name,Transform parent,string label,string sprite,float w,float h,int size,bool home=false)
    {
        var t=NewRect(name,parent);t.sizeDelta=new Vector2(w,h);var img=AddSpriteImage(t,sprite);
        var b=t.gameObject.AddComponent<Button>();b.targetGraphic=img;
        var txt=Label("Label",t,label,size,Hex("#123253"),w-12,h-12);txt.alignment=TextAlignmentOptions.Center;
        return b;
    }
    private static TMP_InputField Input(string name,Transform parent,string placeholder,float w,float h,bool digits)
    {
        var t=NewRect(name,parent);t.sizeDelta=new Vector2(w,h);AddSpriteImage(t,"Input");
        var inner=NewRect("Text Area",t);StretchMargins(inner,24,12,24,12);inner.gameObject.AddComponent<RectMask2D>();
        var txt=Label("Text",inner,"",28,Navy,w-60,h-22);Stretch(Rect(txt));txt.alignment=TextAlignmentOptions.MidlineLeft;
        var ph=Label("Placeholder",inner,placeholder,24,Hex("#768EAB"),w-60,h-22);Stretch(Rect(ph));ph.alignment=TextAlignmentOptions.MidlineLeft;
        var field=t.gameObject.AddComponent<TMP_InputField>();field.textViewport=inner;field.textComponent=(TextMeshProUGUI)txt;field.placeholder=(Graphic)ph;
        field.lineType=TMP_InputField.LineType.SingleLine;
        if(digits)field.contentType=TMP_InputField.ContentType.IntegerNumber;
        return field;
    }
}
#endif
