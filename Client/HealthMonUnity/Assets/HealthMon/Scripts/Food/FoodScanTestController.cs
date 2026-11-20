using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.Networking;

// Only attached to FoodScanTestScene. Does not change production connection settings.
public sealed class FoodScanTestController : MonoBehaviour
{
    [SerializeField] TMP_FontAsset font;
    TMP_InputField address;
    TMP_Text status;
    RectTransform cameraView, results, content, safeRoot;
    Rect lastSafeArea;
    ScrollRect resultScroll;
    RawImage preview;
    AspectRatioFitter previewAspect;
    Button shoot, analyze, connect, paste;
    WebCamTexture webcam;
    Texture2D captured;
    byte[] jpg;
    UnityWebRequest request;
    bool busy, cameraStarting, cameraReady;
    TMP_Text cameraStatus;
    [SerializeField] string deviceServerUrl = "http://192.168.219.106:8001";
    readonly List<Texture2D> decoded = new List<Texture2D>();
    void Start()
    {
        if (gameObject.scene.name != "FoodScanTestScene") { enabled=false; return; }
        if (EventSystem.current==null) new GameObject("TestEventSystem",typeof(EventSystem),typeof(InputSystemUIInputModule));
        var canvas=new GameObject("FoodScanTestUI",typeof(RectTransform),typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));
        canvas.transform.SetParent(transform,false);
        canvas.GetComponent<Canvas>().renderMode=RenderMode.ScreenSpaceOverlay;
        var scaler=canvas.GetComponent<CanvasScaler>(); scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution=new Vector2(720,1280); scaler.matchWidthOrHeight=.5f;
        safeRoot=Rect("SafeArea",canvas.transform); ApplySafeArea();
        var root=Vertical("Screen",safeRoot); Stretch(root); root.gameObject.AddComponent<Image>().color=new Color(.95f,.97f,.97f);
        var layout=root.GetComponent<VerticalLayoutGroup>(); layout.padding=new RectOffset(24,24,30,24);
        Label(root,"음식 촬영 · 분석 테스트",32,52);
        var row=Row(root,58);
        var input=Rect("ServerAddress",row); input.gameObject.AddComponent<Image>().color=Color.white;
        address=input.gameObject.AddComponent<TMP_InputField>(); var area=Rect("TextArea",input); Stretch(area); area.offsetMin=new Vector2(10,4);area.offsetMax=new Vector2(-10,-4);
        address.textViewport=area; var text=Label(area,"",22,48);Stretch(text.rectTransform);address.textComponent=text;
        string defaultUrl=Application.isEditor?"http://127.0.0.1:8001":deviceServerUrl;
        address.text=PlayerPrefs.GetString("FoodScanTest.Server",defaultUrl);
        if(!Application.isEditor && (address.text.Contains("127.0.0.1")||address.text.Contains("192.168.80.1")))address.text=defaultUrl;
        address.keyboardType=TouchScreenKeyboardType.URL;
        address.lineType=TMP_InputField.LineType.SingleLine;
        connect=Btn(row,"연결 확인",()=>StartCoroutine(Check()));
        paste=Btn(root,"붙여넣기",PasteServerAddress);
        status=Label(root,"PC: 웹캠 촬영 또는 테스트 사진 / 휴대폰: 후면 카메라",21,76);
        cameraView=Vertical("CameraView",root); Flex(cameraView);
        var frame=Rect("CameraPreview",cameraView);Flex(frame);frame.gameObject.AddComponent<Image>().color=new Color(.1f,.13f,.16f);
        var image=Rect("Preview",frame);Stretch(image);preview=image.gameObject.AddComponent<RawImage>();preview.raycastTarget=false;
        previewAspect=image.gameObject.AddComponent<AspectRatioFitter>();previewAspect.aspectMode=AspectRatioFitter.AspectMode.FitInParent;
        cameraStatus=Label(cameraView,"카메라 준비 중…",23,65);
        Btn(cameraView,"카메라 다시 연결",()=>{if(!busy&&!cameraStarting)StartCoroutine(StartCamera());});
        var buttons=Row(cameraView,66);shoot=Btn(buttons,"촬영",Capture);Btn(buttons,"다시 촬영",Live);analyze=Btn(buttons,"사진 분석",()=>StartCoroutine(Analyze()));
#if UNITY_EDITOR
        Btn(cameraView,"테스트 사진 불러오기 (food.jpg)",LoadTest);
#endif
        results=Vertical("Results",root);Flex(results);
        Btn(results,"카메라로 돌아가기",()=>{if(!busy){results.gameObject.SetActive(false);cameraView.gameObject.SetActive(true);Live();}});
        var scrollRect=Rect("ResultScroll",results);Flex(scrollRect);
        var scroll=scrollRect.gameObject.AddComponent<ScrollRect>();resultScroll=scroll;scroll.movementType=ScrollRect.MovementType.Clamped;scroll.horizontal=false;scroll.scrollSensitivity=35;
        var viewport=Rect("Viewport",scrollRect);Stretch(viewport);viewport.gameObject.AddComponent<Image>().color=Color.white;viewport.gameObject.AddComponent<RectMask2D>();
        content=Vertical("Content",viewport);content.anchorMin=new Vector2(0,1);content.anchorMax=Vector2.one;content.pivot=new Vector2(.5f,1);content.offsetMin=content.offsetMax=Vector2.zero;
        content.gameObject.AddComponent<ContentSizeFitter>().verticalFit=ContentSizeFitter.FitMode.PreferredSize;
        scroll.content=content;scroll.viewport=viewport;results.gameObject.SetActive(false);
        SetBusy(false);StartCoroutine(StartCamera());
    }
    IEnumerator StartCamera()
    {
        if(cameraStarting)yield break;
        cameraStarting=true;cameraReady=false;shoot.interactable=false;
        cameraStatus.text="카메라 권한 확인 중…";
#if UNITY_ANDROID && !UNITY_EDITOR
        if(!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera))
        {
            bool answered=false;
            var callbacks=new UnityEngine.Android.PermissionCallbacks();
            callbacks.PermissionGranted += _ => answered=true;
            callbacks.PermissionDenied += _ => answered=true;
            UnityEngine.Android.Permission.RequestUserPermission(UnityEngine.Android.Permission.Camera,callbacks);
            float until=Time.realtimeSinceStartup+60;
            while(!answered && !UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera) && Time.realtimeSinceStartup<until)yield return null;
        }
        bool permitted=UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera);
#else
        yield return Application.RequestUserAuthorization(UserAuthorization.WebCam);
        bool permitted=Application.HasUserAuthorization(UserAuthorization.WebCam);
#endif
        if(!permitted){cameraStatus.text="카메라 권한 없음: 설정 → 앱 → 이 앱 → 권한 → 카메라 허용 후 다시 연결하세요.";cameraStarting=false;yield break;}
        if(webcam!=null){webcam.Stop();Destroy(webcam);webcam=null;}
        jpg=null;analyze.interactable=false;
        // Give Android time to resume its camera service after the permission dialog.
        yield return null;
        var devices=WebCamTexture.devices;
        if(devices.Length==0){cameraStatus.text="카메라를 찾지 못했습니다. 다른 카메라 앱을 닫고 다시 연결하세요.";cameraStarting=false;yield break;}
        var device=devices[0];foreach(var d in devices)if(!d.isFrontFacing){device=d;break;}
        webcam=new WebCamTexture(device.name,1280,720,30);
        preview.texture=webcam;
        cameraStatus.text="카메라 영상 수신 중…";
        string startError=null;
        try{webcam.Play();}catch(Exception e){startError=e.Message;}
        if(startError!=null){cameraStatus.text="카메라 시작 실패: "+startError;cameraStarting=false;yield break;}
        float deadline=Time.realtimeSinceStartup+15;
        while((webcam.width<32 || !webcam.didUpdateThisFrame) && Time.realtimeSinceStartup<deadline)yield return null;
        cameraReady=webcam.width>=32 && webcam.didUpdateThisFrame;
        cameraStarting=false;
        shoot.interactable=!busy&&cameraReady;
        cameraStatus.text=cameraReady?"음식과 접시가 모두 보이도록 촬영해 주세요":"카메라 영상 수신 실패. 권한 및 다른 카메라 앱을 확인하고 다시 연결하세요.";
    }

    void ApplySafeArea()
    {
        lastSafeArea=Screen.safeArea;
        safeRoot.anchorMin=new Vector2(lastSafeArea.xMin/Screen.width,lastSafeArea.yMin/Screen.height);
        safeRoot.anchorMax=new Vector2(lastSafeArea.xMax/Screen.width,lastSafeArea.yMax/Screen.height);
        safeRoot.offsetMin=safeRoot.offsetMax=Vector2.zero;
    }
    void Update()
    {
        if(safeRoot!=null && lastSafeArea!=Screen.safeArea)ApplySafeArea();
        if(preview==null || webcam==null || preview.texture!=webcam || webcam.width<32)return;
        int angle=webcam.videoRotationAngle;
        preview.rectTransform.localEulerAngles=new Vector3(0,0,-angle);
        preview.rectTransform.localScale=new Vector3(1,webcam.videoVerticallyMirrored?-1:1,1);
        previewAspect.aspectRatio=(float)webcam.width/webcam.height;
        // Fit the rotated camera rectangle inside the portrait viewport.
        if(angle==90||angle==270){var parent=(RectTransform)preview.transform.parent;float scale=Mathf.Min(parent.rect.width/preview.rectTransform.rect.height,parent.rect.height/preview.rectTransform.rect.width);preview.rectTransform.localScale*=scale;}
    }
    void Live(){if(busy)return;if(webcam==null||!cameraReady){if(!cameraStarting)StartCoroutine(StartCamera());return;}jpg=null;analyze.interactable=false;if(webcam!=null&&!webcam.isPlaying)webcam.Play();preview.texture=webcam;status.text=webcam!=null?"촬영 버튼을 눌러주세요.":"카메라 준비 중 또는 사용할 수 없음";}
    void Capture()
    {
        if(busy)return;
        if(!cameraReady||webcam==null||!webcam.isPlaying||webcam.width<32){status.text="카메라가 아직 준비되지 않았습니다.";return;}
        int w=webcam.width,h=webcam.height,a=webcam.videoRotationAngle;bool swap=a==90||a==270;
        var pixels=webcam.GetPixels32();var output=new Color32[pixels.Length];int ow=swap?h:w,oh=swap?w:h;
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){
            int sy=webcam.videoVerticallyMirrored?h-1-y:y;int dx=x,dy=y;
            if(a==90){dx=y;dy=w-1-x;}else if(a==180){dx=w-1-x;dy=h-1-y;}else if(a==270){dx=h-1-y;dy=x;}
            output[dy*ow+dx]=pixels[sy*w+x];
        }
        var texture=new Texture2D(ow,oh,TextureFormat.RGB24,false);texture.SetPixels32(output);texture.Apply();SetPhoto(texture);
    }
    void SetPhoto(Texture2D texture)
    {
        if(captured!=null)Destroy(captured);captured=texture;if(webcam!=null)webcam.Pause();jpg=texture.EncodeToJPG(85);preview.texture=texture;
        preview.rectTransform.localRotation=Quaternion.identity;preview.rectTransform.localScale=Vector3.one;previewAspect.aspectRatio=(float)texture.width/texture.height;
        analyze.interactable=true;status.text="촬영 완료. 사진 분석을 눌러주세요.";
    }
    void LoadTest(){if(busy)return;Texture2D t=null;try{t=new Texture2D(2,2);if(!t.LoadImage(File.ReadAllBytes(Path.Combine(Application.dataPath,"HealthMon/Scripts/Food/food.jpg"))))throw new Exception("이미지 형식 오류");SetPhoto(t);}catch(Exception e){if(t!=null)Destroy(t);status.text="테스트 사진 오류: "+e.Message;}}
    void PasteServerAddress()
    {
        if(busy)return;
        string copied=GUIUtility.systemCopyBuffer;
        if(string.IsNullOrWhiteSpace(copied))
        {
            status.text="복사한 주소가 없습니다. 서버 주소를 먼저 복사해 주세요.";
            return;
        }
        address.text=copied.Trim();
        status.text="서버 주소를 붙여넣었습니다. 연결 확인을 눌러주세요.";
    }
    string Url()
    {
        var s=address.text.Trim().Replace(" ","").TrimEnd('/');
        if(!s.Contains("://"))s="http://"+s;
        if(!Uri.TryCreate(s,UriKind.Absolute,out var u)||(u.Scheme!="http"&&u.Scheme!="https")){status.text="서버 주소 형식: http://PC주소:8001";return null;}
        if(u.Scheme=="https"&&u.Port==8001){status.text="현재 음식 서버는 HTTPS를 지원하지 않습니다. http://PC주소:8001로 입력하세요.";return null;}
        if(!Application.isEditor&&(u.IsLoopback||u.Host=="192.168.80.1")){status.text="PC의 실제 LAN 주소를 사용하세요: "+deviceServerUrl;return null;}
        address.text=s;return s;
    }
    void SetBusy(bool b){busy=b;address.interactable=!b;connect.interactable=!b;paste.interactable=!b;shoot.interactable=!b&&cameraReady;analyze.interactable=!b&&jpg!=null;}
    IEnumerator Check()
    {
        if(busy)yield break;string url=Url();if(url==null)yield break;SetBusy(true);status.text="서버 연결 확인 중…";
        using(var r=UnityWebRequest.Get(url+"/health")){request=r;r.timeout=10;yield return r.SendWebRequest();request=null;
            if(r.result==UnityWebRequest.Result.Success&&r.downloadHandler.text.Contains("healthmon-multifood")){PlayerPrefs.SetString("FoodScanTest.Server",url);PlayerPrefs.Save();status.text="음식 AI 서버 연결 성공. 사진을 촬영해 주세요.";}
            else status.text="연결 실패: "+url+"\n음식 AI 서버의 8001 포트를 확인하세요. "+(r.error??"다른 종류의 서버입니다.");
        }SetBusy(false);
    }
    IEnumerator Analyze()
    {
        if(busy||jpg==null)yield break;string url=Url();if(url==null)yield break;
        if(jpg.Length>8*1024*1024){status.text="사진 크기는 8MB 이하여야 합니다.";yield break;}
        SetBusy(true);status.text="음식별 이름 · 중량 · 영양소 분석 중… (최대 5분)";
        var form=new WWWForm();form.AddBinaryData("image",jpg,"food.jpg","image/jpeg");
        using(var r=UnityWebRequest.Post(url+"/vision/analyze",form)){
            request=r;r.timeout=330;yield return r.SendWebRequest();request=null;
            if(r.result!=UnityWebRequest.Result.Success)status.text="분석 실패 ("+r.responseCode+"): "+r.error+". 연결 확인 후 다시 시도해 주세요.";
            else try{var data=JsonUtility.FromJson<VisionAnalysis>(r.downloadHandler.text);MultiFoodScanPanel.Validate(data);Render(data);PlayerPrefs.SetString("FoodScanTest.Server",url);PlayerPrefs.Save();}catch(Exception e){status.text="결과 처리 오류: "+e.Message;}
        }SetBusy(false);
    }
    Texture2D Decode(string data){var t=new Texture2D(2,2);try{if(!t.LoadImage(Convert.FromBase64String(data)))throw new Exception("이미지 오류");decoded.Add(t);return t;}catch{Destroy(t);throw;}}
    static string Num(float n,bool has,string unit){return has?n.ToString("0.#")+unit:"정보 없음";}
    void Render(VisionAnalysis data)
    {
        foreach(Transform c in content){c.gameObject.SetActive(false);Destroy(c.gameObject);}foreach(var t in decoded)Destroy(t);decoded.Clear();
        Label(content,"분석 결과 · "+data.foods.Length+"개 음식",30,55);
        Picture(content,Decode(data.annotated_base64),420);
        float total=0;int counted=0;
        foreach(var food in data.foods)if(food.has_weight&&food.per100.has_calories){total+=food.grams/100f*food.per100.calories;counted++;}
        Label(content,"전체 열량  "+total.ToString("0.#")+" kcal"+(counted<data.foods.Length?" (정보 있는 음식 합계)":""),28,64);
        foreach(var f in data.foods){
            var card=Vertical("Food_"+f.id,content);card.gameObject.AddComponent<Image>().color=new Color(.94f,.97f,.96f);card.GetComponent<VerticalLayoutGroup>().padding=new RectOffset(16,16,14,14);
            var heading=Row(card,150);
            Picture(heading,Decode(f.crop_base64),150);
            var details=Vertical("FoodTitle",heading);
            Label(details,f.name,28,80);
            Label(details,"음식 #"+f.id,20,35);
            Label(card,"중량  "+Num(f.grams,f.has_weight," g"),24,45);
            var n=f.per100;float factor=f.grams/100f;
            Label(card,"열량  "+Num(n.calories*factor,f.has_weight&&n.has_calories," kcal"),28,48);
            Label(card,"탄수화물  "+Num(n.carbs*factor,f.has_weight&&n.has_carbs," g")+"\n단백질  "+Num(n.protein*factor,f.has_weight&&n.has_protein," g")+"\n지방  "+Num(n.fat*factor,f.has_weight&&n.has_fat," g"),24,110);
            Label(card,"100 g 기준  ·  "+Num(n.calories,n.has_calories," kcal")+"\n영양 정보: "+(string.IsNullOrEmpty(f.nutrition_source)?"자료 없음":f.nutrition_source),20,100);
        }
        cameraView.gameObject.SetActive(false);results.gameObject.SetActive(true);Canvas.ForceUpdateCanvases();content.anchoredPosition=Vector2.zero;resultScroll.StopMovement();resultScroll.verticalNormalizedPosition=1;
        status.text=data.foods.Length==0?"음식이 검출되지 않았습니다. 가까이서 다시 촬영해 주세요.":"분석 완료. 아래로 스크롤하면 음식별 정보를 볼 수 있습니다.";
    }
    void Picture(Transform parent,Texture2D t,float height){var r=Rect("Photo",parent);Height(r,height);var child=Rect("Image",r);Stretch(child);var image=child.gameObject.AddComponent<RawImage>();image.texture=t;image.raycastTarget=false;var fit=child.gameObject.AddComponent<AspectRatioFitter>();fit.aspectMode=AspectRatioFitter.AspectMode.FitInParent;fit.aspectRatio=(float)t.width/t.height;}
    void OnApplicationPause(bool paused){if(webcam==null)return;if(paused)webcam.Pause();else if(jpg==null)webcam.Play();}
    void OnDestroy(){if(request!=null)request.Abort();if(webcam!=null){webcam.Stop();Destroy(webcam);}if(captured!=null)Destroy(captured);foreach(var t in decoded)if(t!=null)Destroy(t);}
    static RectTransform Rect(string name,Transform parent){var o=new GameObject(name,typeof(RectTransform));o.transform.SetParent(parent,false);return (RectTransform)o.transform;}
    static void Stretch(RectTransform r){r.anchorMin=Vector2.zero;r.anchorMax=Vector2.one;r.offsetMin=r.offsetMax=Vector2.zero;}
    static void Height(RectTransform r,float h){var e=r.gameObject.AddComponent<LayoutElement>();e.minHeight=e.preferredHeight=h;}
    static void Flex(RectTransform r){var e=r.gameObject.AddComponent<LayoutElement>();e.flexibleHeight=1;e.minHeight=120;}
    static RectTransform Vertical(string name,Transform parent){var r=Rect(name,parent);var l=r.gameObject.AddComponent<VerticalLayoutGroup>();l.spacing=12;l.childControlHeight=true;l.childForceExpandHeight=false;l.childForceExpandWidth=true;return r;}
    static RectTransform Row(Transform parent,float h){var r=Rect("Controls",parent);Height(r,h);var l=r.gameObject.AddComponent<HorizontalLayoutGroup>();l.spacing=10;l.childForceExpandWidth=true;l.childControlWidth=true;return r;}
    TMP_Text Label(Transform parent,string text,int size,float h){var r=Rect("Label",parent);Height(r,h);var t=r.gameObject.AddComponent<TextMeshProUGUI>();t.font=font;t.text=text;t.fontSize=size;t.color=new Color(.12f,.18f,.21f);t.raycastTarget=false;t.richText=false;t.enableWordWrapping=true;t.enableAutoSizing=true;t.fontSizeMin=16;t.fontSizeMax=size;return t;}
    Button Btn(Transform parent,string label,UnityEngine.Events.UnityAction action){var r=Rect(label,parent);Height(r,58);var i=r.gameObject.AddComponent<Image>();i.color=new Color(.73f,.9f,.82f);var b=r.gameObject.AddComponent<Button>();b.targetGraphic=i;b.onClick.AddListener(action);var t=Label(r,label,22,58);Stretch(t.rectTransform);t.alignment=TextAlignmentOptions.Center;return b;}
}
