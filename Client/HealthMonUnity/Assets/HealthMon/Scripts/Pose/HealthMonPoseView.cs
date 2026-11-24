using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>HealthMon presentation only. Counts and tracking messages come from the pose session.</summary>
public sealed class HealthMonPoseView : MonoBehaviour
{
    public TMP_FontAsset font;
    public Sprite background, card, lightCard, blueButton, mintButton, goldButton, activityIcon;
    public event Action<int> ExerciseSelected;
    public event Action Prepare, StartWorkout, PauseWorkout, FinishWorkout, Retry, Close, Retarget, SwitchCamera;
    public GameObject selection, cameraPage, resultPage;
    public RawImage preview;
    public TMP_Text status, count, angles, exerciseTitle, message, resultCount, resultTime, resultNote, sourceLabel;
    public Button startButton, pauseButton, finishButton, retryButton, switchCameraButton;
    public TMP_Text pauseLabel;
    private Button[] choices;
    private TMP_Text[] choiceLabels;
    private GameObject[] choiceBadges;
    private TMP_Text guide, stepLabel;
    private RectTransform safeArea;
    private bool built;
    private static readonly Color Navy = new Color32(30, 54, 91, 255);
    private static readonly Color Ice = new Color32(221, 244, 255, 255);
    public static readonly string[] Names = { "스쿼트", "팔굽혀펴기", "덤벨 컬" };
    public static readonly string[] Keys = { "squat", "pushup", "curl" };
    public static readonly string[] Guides = {
        "골반 · 무릎 · 발목을 화면 안에 배치\n준비 자세: 다리를 펴고 제자리 유지",
        "어깨 · 팔꿈치 · 손목이 보이도록 측면 배치\n준비 자세: 팔을 펴고 몸통 정렬",
        "어깨 · 팔꿈치 · 손목을 화면 안에 배치\n준비 자세: 팔을 내리고 위팔 고정" };

    public void Build()
    {
        if (built) return;
        built = true;
        var backdrop = gameObject.AddComponent<Image>(); backdrop.sprite = background; backdrop.color = Color.white;
        safeArea = Rect("SafeArea", transform, 0, 0, 1, 1);
        var header = Panel("Header", safeArea, .045f, .865f, .955f, .985f, card);
        Label("Brand", header, "HEALTHMON  /  MOVE", 24, Ice, .045f,.67f,.74f,.91f);
        Label("Title", header, "헬스몬 트레이닝", 46, Color.white, .045f,.22f,.81f,.70f);
        Button("Close", header, "닫기", blueButton, .81f,.22f,.97f,.75f, () => Close?.Invoke(), 28);
        stepLabel = Label("Steps", safeArea, "01 훈련 선택   ·   02 자세 준비   ·   03 훈련 시작", 25, Ice, .07f,.824f,.94f,.861f);

        selection = Rect("Selection", safeArea, .05f,.04f,.95f,.815f).gameObject;
        Label("Heading", selection.transform, "훈련 선택", 38, Color.white, .015f,.91f,.99f,.99f);
        Label("Intro", selection.transform, "정확한 동작으로 기록에 도전", 26, Ice, .015f,.86f,.99f,.92f);
        choices = new Button[3]; choiceLabels = new TMP_Text[3]; choiceBadges = new GameObject[3];
        string[] descriptions = { "하체 훈련  ·  골반부터 발목까지", "상체 훈련  ·  측면 촬영", "팔 훈련  ·  좌우 개별 카운트" };
        for (int i=0;i<3;i++)
        {
            int choice=i; float y=.66f-i*.195f;
            var button = Button("Exercise_"+Keys[i], selection.transform, "", card, 0,y,1,y+.175f, () => ExerciseSelected?.Invoke(choice));
            choices[i]=button;
            Label("Number", button.transform, "0"+(i+1), 38, Ice, .035f,.25f,.14f,.80f);
            Label("Name", button.transform, Names[i], 39, Color.white, .19f,.47f,.80f,.88f);
            Label("Description", button.transform, descriptions[i], 25, Ice, .19f,.15f,.88f,.46f);
            var badge=Panel("SelectedBadge",button.transform,.79f,.55f,.96f,.87f,goldButton);choiceBadges[i]=badge.gameObject;
            choiceLabels[i]=Label("Selected", badge, "선택됨", 23, Navy, .03f,.08f,.97f,.92f,TextAlignmentOptions.Center);
        }
        var tip=Panel("Tip", selection.transform, 0,.12f,1,.255f, lightCard);
        guide=Label("Guide", tip, Guides[0], 27, Navy, .045f,.10f,.955f,.90f);
        Button("Prepare", selection.transform, "훈련 준비", mintButton, .05f,0,.95f,.105f, () => Prepare?.Invoke(), 34);

        cameraPage=Rect("CameraPage",safeArea,.05f,.035f,.95f,.815f).gameObject;
        exerciseTitle=Label("Exercise",cameraPage.transform,Names[0],38,Color.white,0,.925f,.65f,1);
        switchCameraButton=Button("SwitchCamera",cameraPage.transform,"카메라 전환",blueButton,.65f,.925f,1,1,() => SwitchCamera?.Invoke(),23);
        var cameraCard=Panel("CameraCard",cameraPage.transform,0,.495f,1,.92f,card);
        var cameraInset=Panel("CameraInset",cameraCard,.025f,.04f,.975f,.96f,null);
        cameraInset.GetComponent<Image>().color=new Color32(13,29,51,255);
        var raw=Rect("Preview",cameraInset,0,0,1,1); preview=raw.gameObject.AddComponent<RawImage>(); preview.color=Color.white; preview.raycastTarget=false;preview.enabled=false;
        var aspect=raw.gameObject.AddComponent<AspectRatioFitter>(); aspect.aspectMode=AspectRatioFitter.AspectMode.FitInParent; aspect.aspectRatio=4f/3;
        sourceLabel=Label("Source",cameraCard,"카메라 준비 중",23,Ice,.04f,.02f,.96f,.12f);
        var metrics=Panel("Metrics",cameraPage.transform,0,.315f,1,.48f,lightCard);
        Label("CountCaption",metrics,"완료 횟수",25,Navy,.04f,.68f,.55f,.94f);
        count=Label("Count",metrics,"—",63,Navy,.04f,.05f,.60f,.71f);
        status=Label("Status",metrics,"촬영 준비",28,Navy,.60f,.52f,.96f,.92f);
        angles=Label("Angles",metrics,"관절 확인 전",23,Navy,.60f,.08f,.96f,.54f);
        message=Label("Message",cameraPage.transform,Guides[0],27,Ice,.015f,.135f,.985f,.305f);
        startButton=Button("StartWorkout",cameraPage.transform,"훈련 시작",mintButton,.05f,.025f,.95f,.12f,() => StartWorkout?.Invoke(),34);
        pauseButton=Button("Pause",cameraPage.transform,"일시정지",goldButton,0,.025f,.38f,.12f,() => PauseWorkout?.Invoke(),29);
        pauseLabel=pauseButton.GetComponentInChildren<TMP_Text>();
        finishButton=Button("Finish",cameraPage.transform,"훈련 종료",mintButton,.40f,.025f,1,.12f,() => FinishWorkout?.Invoke(),32);
        retryButton=Button("Retarget",cameraPage.transform,"대상 다시 찾기",blueButton,.65f,.925f,1,1,() => Retarget?.Invoke(),23);

        resultPage=Rect("Result",safeArea,.05f,.065f,.95f,.805f).gameObject;
        Label("ResultHeading",resultPage.transform,"훈련 완료",40,Color.white,.01f,.84f,.99f,.98f,TextAlignmentOptions.Center);
        var resultCard=Panel("ResultCard",resultPage.transform,0,.28f,1,.81f,lightCard);
        Label("ResultCaption",resultCard,"완료 횟수",30,Navy,.05f,.78f,.95f,.93f,TextAlignmentOptions.Center);
        resultCount=Label("ResultCount",resultCard,"0회",82,Navy,.05f,.43f,.95f,.78f,TextAlignmentOptions.Center);
        resultTime=Label("ResultTime",resultCard,"스쿼트  ·  00:00",32,Navy,.05f,.24f,.95f,.43f,TextAlignmentOptions.Center);
        resultNote=Label("ResultNote",resultCard,"훈련 기록 저장 완료",26,Navy,.05f,.07f,.95f,.24f,TextAlignmentOptions.Center);
        Label("ResultTip",resultPage.transform,"다음 훈련에 도전",28,Ice,.02f,.17f,.98f,.26f,TextAlignmentOptions.Center);
        Button("Again",resultPage.transform,"다음 훈련",mintButton,0,.025f,.59f,.135f,()=>Retry?.Invoke(),31);
        Button("Done",resultPage.transform,"홈으로",goldButton,.62f,.025f,1,.135f,()=>Close?.Invoke(),31);
        SelectExercise(0); ShowSelection(); ApplySafeArea();
    }
    private void Update() { if (safeArea != null) ApplySafeArea(); }
    private void ApplySafeArea()
    {
        var r=Screen.safeArea; if(Screen.width<=0||Screen.height<=0)return;
        safeArea.anchorMin=new Vector2(r.x/Screen.width,r.y/Screen.height);
        safeArea.anchorMax=new Vector2(r.xMax/Screen.width,r.yMax/Screen.height);
    }
    public void SelectExercise(int index)
    {
        for(int i=0;i<choices.Length;i++) { choices[i].image.color=i==index?Color.white:new Color(.73f,.81f,.94f); choiceBadges[i].SetActive(i==index); }
        guide.text=Guides[index]; exerciseTitle.text=Names[index]; message.text=Guides[index];
    }
    public void ShowSelection() { selection.SetActive(true); cameraPage.SetActive(false); resultPage.SetActive(false); stepLabel.text="01 훈련 선택   ·   02 자세 준비   ·   03 훈련 시작"; }
    public void ShowCamera(bool running)
    {
        selection.SetActive(false); cameraPage.SetActive(true); resultPage.SetActive(false);
        startButton.gameObject.SetActive(!running); pauseButton.gameObject.SetActive(running); finishButton.gameObject.SetActive(running); retryButton.gameObject.SetActive(running);
        switchCameraButton.gameObject.SetActive(!running);
        stepLabel.text=running?"03 훈련 중  ·  준비 → 굽힘 → 복귀":"02 자세 준비  ·  필요한 관절을 화면 안에 배치";
    }
    public void ShowResult() { selection.SetActive(false); cameraPage.SetActive(false); resultPage.SetActive(true); stepLabel.text="RESULT  ·  훈련 결과"; }
    public void SetPreview(Texture texture)
    {
        preview.texture=texture;
        preview.enabled=texture!=null;
        if(texture!=null) preview.GetComponent<AspectRatioFitter>().aspectRatio=(float)texture.width/texture.height;
    }
    private RectTransform Rect(string name,Transform parent,float x0,float y0,float x1,float y1)
    {
        var r=new GameObject(name,typeof(RectTransform)).GetComponent<RectTransform>(); r.SetParent(parent,false);
        r.anchorMin=new Vector2(x0,y0); r.anchorMax=new Vector2(x1,y1); r.offsetMin=r.offsetMax=Vector2.zero; return r;
    }
    private RectTransform Panel(string name,Transform parent,float x0,float y0,float x1,float y1,Sprite sprite)
    {
        var r=Rect(name,parent,x0,y0,x1,y1); var image=r.gameObject.AddComponent<Image>(); image.sprite=sprite; image.type=Image.Type.Sliced; return r;
    }
    private TMP_Text Label(string name,Transform parent,string text,int size,Color color,float x0,float y0,float x1,float y1,TextAlignmentOptions align=TextAlignmentOptions.Left)
    {
        var r=Rect(name,parent,x0,y0,x1,y1); var t=r.gameObject.AddComponent<TextMeshProUGUI>(); t.font=font; t.text=text;
        t.fontSize=size; t.color=color; t.alignment=align; t.enableAutoSizing=true; t.fontSizeMax=size; t.fontSizeMin=size*.75f; t.raycastTarget=false; return t;
    }
    private Button Button(string name,Transform parent,string text,Sprite sprite,float x0,float y0,float x1,float y1,Action action,int size=30)
    {
        var r=Panel(name,parent,x0,y0,x1,y1,sprite); var b=r.gameObject.AddComponent<Button>(); b.targetGraphic=r.GetComponent<Image>(); b.onClick.AddListener(()=>action());
        var c=b.colors;c.disabledColor=new Color(.45f,.52f,.62f);c.pressedColor=new Color(.75f,.88f,1);b.colors=c;
        Label("Label",r,text,size,sprite==mintButton||sprite==goldButton?Navy:Color.white,.035f,.08f,.965f,.92f,TextAlignmentOptions.Center); return b;
    }
}
