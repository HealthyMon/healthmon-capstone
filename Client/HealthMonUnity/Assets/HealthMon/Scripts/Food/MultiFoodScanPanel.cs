using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;

[Serializable] public class VisionNutrients
{
    public float calories, carbs, protein, fat;
    public bool has_calories, has_carbs, has_protein, has_fat;
}
[Serializable] public class VisionFood
{
    public int id, class_id;
    public string name, weight_status, crop_base64, nutrition_source, nutrition_confidence;
    public float grams, name_confidence;
    public bool has_weight, name_edited, weight_edited;
    public float[] bbox;
    public VisionNutrients per100;
    public VisionNutrients nutrients;
}
[Serializable] public class VisionAnalysis
{
    public int schema_version, image_width, image_height;
    public string analysis_id, annotated_base64, original_base64;
    public VisionFood[] foods;
}
[Serializable] public class VisionCatalogItem
{
    public int class_id;
    public float typical_serving_weight_g;
    public string name, nutrition_source, nutrition_confidence;
    public VisionNutrients per100;
}
[Serializable] public class VisionCatalog { public VisionCatalogItem[] items; }

// Attached to MainARScene/FoodScanPanel. Analysis is independent of pet record submission.
public class MultiFoodScanPanel : MonoBehaviour
{
    [SerializeField] private ARFoodCameraCapture cameraCapture;
    [SerializeField] private string defaultServerUrl = "http://127.0.0.1:8001";
    [SerializeField] private GameObject originalCaptureView, originalCandidateView, originalResultView;
    [SerializeField] private Button originalCaptureButton, originalAnalyzeButton;
    [SerializeField] private TMP_Text originalStatus;
    [SerializeField] private RawImage originalPreview;
    private Button.ButtonClickedEvent captureClicks, analyzeClicks;
    private TMP_FontAsset font;
    private TMP_InputField endpoint;
    private TMP_Text status;
    private RectTransform root, content, cards, photoFrame, overlays, dialog;
    private RawImage photo;
    private Button capture, retry;
    private VisionAnalysis analysis;
    private Texture2D original, annotated;
    private readonly List<Texture2D> textures = new List<Texture2D>();
    private UnityWebRequest activeRequest;
    private byte[] lastJpg;
    private bool busy, built, changed;
    private int revision;

    private void Awake()
    {
        var sample = GetComponentInChildren<TMP_Text>(true);
        font = sample != null ? sample.font : TMP_Settings.defaultFontAsset;
        root = Rect("MultiFoodView", transform); Stretch(root);
        root.gameObject.AddComponent<Image>().color = new Color(.96f,.97f,.98f);
        var layout = root.gameObject.AddComponent<VerticalLayoutGroup>();
        layout.padding = new RectOffset(18,18,16,16); layout.spacing = 12;
        layout.childControlHeight = true; layout.childForceExpandHeight = false;
        Text(root,"음식 사진 분석",32,48);
        var addressRow = Row(root,54);
        endpoint = Input(addressRow,PlayerPrefs.GetString("VisionServerUrl",defaultServerUrl),"AI 서버 주소",false);
        Button(addressRow,"주소 저장",()=> {
            if (BaseUrl()!=null) { PlayerPrefs.SetString("VisionServerUrl",endpoint.text.Trim()); PlayerPrefs.Save(); Status("서버 주소를 저장했습니다."); }
        },130);
        var controls = Row(root,58);
        capture = Button(controls,"다시 촬영",ShowCapture);
        retry = Button(controls,"다시 분석",()=> {if(lastJpg!=null) StartCoroutine(Analyze(lastJpg));});
        Button(controls,"결과 저장",Save);
        Button(controls,"닫기",()=>gameObject.SetActive(false),85);
        status = Text(root,"사진을 촬영해 주세요. PC에서는 Food/food.jpg를 사용합니다.",20,55);
        content = Scroll(root);
        photoFrame = Rect("PhotoFrame",content); Height(photoFrame,360);
        var imageRect=Rect("AnnotatedPhoto",photoFrame); Stretch(imageRect);
        photo=imageRect.gameObject.AddComponent<RawImage>();photo.color=Color.white;
        photo.raycastTarget=false;
        var fitter=imageRect.gameObject.AddComponent<AspectRatioFitter>();
        fitter.aspectMode=AspectRatioFitter.AspectMode.FitInParent;
        overlays=Rect("FoodBoxes",imageRect);Stretch(overlays);
        cards=Vertical("FoodCards",content);
        built=true;
        if(originalCaptureButton!=null)
        {
            captureClicks=originalCaptureButton.onClick;
            originalCaptureButton.onClick=new Button.ButtonClickedEvent();
            originalCaptureButton.onClick.AddListener(Capture);
        }
        if(originalAnalyzeButton!=null)
        {
            analyzeClicks=originalAnalyzeButton.onClick;
            originalAnalyzeButton.onClick=new Button.ButtonClickedEvent();
            originalAnalyzeButton.onClick.AddListener(()=> {if(lastJpg!=null&&!busy)StartCoroutine(Analyze(lastJpg));});
        }
        ShowCapture();
    }

    private void OnEnable()
    {
        if(cameraCapture==null) cameraCapture=FindAnyObjectByType<ARFoodCameraCapture>();
        if(cameraCapture!=null) {cameraCapture.OnCaptureCompleted+=Captured;cameraCapture.OnCaptureFailed+=CaptureFailed;}
        if(built)ShowCapture();
    }
    private void OnDisable()
    {
        revision++;
        if(cameraCapture!=null) {cameraCapture.OnCaptureCompleted-=Captured;cameraCapture.OnCaptureFailed-=CaptureFailed;}
        if(activeRequest!=null) activeRequest.Abort();
        StopAllCoroutines();activeRequest=null;SetBusy(false);
        if(dialog!=null) Destroy(dialog.gameObject);
    }
    private void OnDestroy()
    {
        if(originalCaptureButton!=null&&captureClicks!=null)originalCaptureButton.onClick=captureClicks;
        if(originalAnalyzeButton!=null&&analyzeClicks!=null)originalAnalyzeButton.onClick=analyzeClicks;
        foreach(var texture in textures) if(texture!=null) Destroy(texture);
    }
    private void Status(string value) {if(status!=null) status.text=value;if(originalStatus!=null)originalStatus.text=value;}
    private void ShowCapture()
    {
        if(busy)return;
        root.gameObject.SetActive(false);
        if(originalCaptureView!=null)originalCaptureView.SetActive(true);
        if(originalCandidateView!=null)originalCandidateView.SetActive(false);
        if(originalResultView!=null)originalResultView.SetActive(false);
        lastJpg=null;
        if(originalPreview!=null){originalPreview.texture=null;originalPreview.gameObject.SetActive(false);}
        SetBusy(false);Status("음식 사진을 촬영해 주세요.");
    }
    private void SetBusy(bool value)
    {
        busy=value;if(!built)return;
        capture.interactable=!value;retry.interactable=!value&&lastJpg!=null;endpoint.interactable=!value;
        if(originalCaptureButton!=null)originalCaptureButton.interactable=!value;
        if(originalAnalyzeButton!=null)originalAnalyzeButton.interactable=!value&&lastJpg!=null;
    }
    private string BaseUrl()
    {
        string value=endpoint.text.Trim().TrimEnd('/');
        if(!Uri.TryCreate(value,UriKind.Absolute,out var uri)||(uri.Scheme!="http"&&uri.Scheme!="https"))
        {Status("http://PC주소:8001 형식의 서버 주소를 입력하세요.");return null;}
        return value;
    }
    private void Capture()
    {
        if(busy)return;
        if(cameraCapture==null){Status("AR 카메라 연결이 없습니다.");return;}
        SetBusy(true);Status("촬영 중…");cameraCapture.Capture();
    }
    private void CaptureFailed(string message){SetBusy(false);Status(message);}
    private void Captured(Texture2D texture,byte[] jpg)
    {
        lastJpg=jpg;SetBusy(false);
        if(originalPreview!=null){originalPreview.texture=texture;originalPreview.gameObject.SetActive(true);}
        Status("촬영 완료. 분석 버튼을 눌러주세요.");
    }
    private IEnumerator Analyze(byte[] jpg)
    {
        if(busy)yield break;
        string url=BaseUrl();if(url==null)yield break;
        if(jpg==null||jpg.Length==0||jpg.Length>8*1024*1024){Status("사진은 8MB 이하이어야 합니다.");yield break;}
        SetBusy(true);Status("음식별 이름·중량·영양소 분석 중…");
        int version=++revision;
        var form=new WWWForm();form.AddBinaryData("image",jpg,"food.jpg","image/jpeg");
        using(var request=UnityWebRequest.Post(url+"/vision/analyze",form))
        {
            activeRequest=request;request.timeout=330;
            yield return request.SendWebRequest();activeRequest=null;SetBusy(false);
            if(version!=revision)yield break;
            if(request.result!=UnityWebRequest.Result.Success)
            {Status("분석 실패: "+request.error+"\n"+request.downloadHandler.text);yield break;}
            try
            {
                var next=JsonUtility.FromJson<VisionAnalysis>(request.downloadHandler.text);
                Validate(next);
                foreach(var texture in textures)if(texture!=null)Destroy(texture);textures.Clear();
                analysis=next;changed=false;
                original=Decode(next.original_base64);annotated=Decode(next.annotated_base64);
                photo.texture=annotated;
                photo.GetComponent<AspectRatioFitter>().aspectRatio=(float)next.image_width/next.image_height;
                RenderCards();Clear(overlays);
                if(originalCaptureView!=null)originalCaptureView.SetActive(false);
                root.gameObject.SetActive(true);
                Status(next.foods.Length==0?"인식된 음식이 없습니다. 가까이서 다시 촬영해 주세요.":next.foods.Length+"개 음식 분석 완료");
            }
            catch(Exception e){Status("결과 처리 실패: "+e.Message);}
        }
    }
    public static void Validate(VisionAnalysis value)
    {
        if(value==null||value.schema_version!=1||value.image_width<=0||value.image_height<=0||value.foods==null)
            throw new FormatException("지원하지 않는 응답입니다.");
        var ids=new HashSet<int>();
        foreach(var f in value.foods)
        {
            if(f==null||!ids.Add(f.id)||f.bbox==null||f.bbox.Length!=4||f.per100==null)
                throw new FormatException("음식 좌표 또는 영양소가 없습니다.");
            foreach(float x in f.bbox)if(float.IsNaN(x)||float.IsInfinity(x)||x<0||x>1)throw new FormatException("잘못된 좌표입니다.");
            if(f.bbox[2]<=f.bbox[0]||f.bbox[3]<=f.bbox[1])throw new FormatException("빈 박스입니다.");
        }
    }
    private Texture2D Decode(string data)
    {
        var texture=new Texture2D(2,2,TextureFormat.RGB24,false);
        try {if(!texture.LoadImage(Convert.FromBase64String(data)))throw new FormatException("이미지를 읽지 못했습니다.");}
        catch {Destroy(texture);throw;}
        textures.Add(texture);return texture;
    }
    private void RenderCards()
    {
        Clear(cards);
        // Reuse decoded crop textures across weight/name edits.
        foreach(var f in analysis.foods)
        {
            Recalculate(f);
            var card=Vertical("Food_"+f.id,cards);
            card.gameObject.AddComponent<Image>().color=Color.white;
            var group=card.GetComponent<VerticalLayoutGroup>();group.padding=new RectOffset(12,12,12,12);
            var top=Row(card,125);
            var cropRect=Rect("Crop",top);Width(cropRect,125);
            var crop=cropRect.gameObject.AddComponent<RawImage>();
            var cached=FindCrop(f.id);
            if(cached==null){cached=Decode(f.crop_base64);cached.name="FoodCrop_"+f.id;}
            crop.texture=cached;crop.raycastTarget=false;
            var summary=Text(top,f.name+"\n중량 "+(f.has_weight?f.grams.ToString("0.0")+" g":"없음")+"\n"+MacroText(f),23,125);
            summary.GetComponent<LayoutElement>().flexibleWidth=1;
            var actions=Row(card,52);
            Button(actions,"음식 이름 변경",()=>OpenNameDialog(f));
            var grams=Input(actions,f.grams.ToString("0.0",CultureInfo.InvariantCulture),"중량(g)",true);
            Button(actions,"중량 변경",()=> {
                if(!float.TryParse(grams.text,NumberStyles.Float,CultureInfo.InvariantCulture,out var mass)||float.IsNaN(mass)||float.IsInfinity(mass)||mass<=0||mass>100000)
                {Status("중량은 0보다 큰 g 단위 숫자로 입력하세요.");return;}
                f.grams=mass;f.has_weight=true;f.weight_edited=true;f.weight_status="user_edited";Edited();
            });
            Button(actions,"제거",()=> {
                var list=new List<VisionFood>(analysis.foods);list.Remove(f);analysis.foods=list.ToArray();Edited();
            },80);
        }
    }
    private Texture2D FindCrop(int id){return textures.Find(t=>t!=null&&t.name=="FoodCrop_"+id);}
    public static void Recalculate(VisionFood f)
    {
        float ratio=f.has_weight?f.grams/100f:0;
        var n=f.per100;
        f.nutrients=new VisionNutrients {calories=n.calories*ratio,carbs=n.carbs*ratio,protein=n.protein*ratio,fat=n.fat*ratio,
            has_calories=f.has_weight&&n.has_calories,has_carbs=f.has_weight&&n.has_carbs,
            has_protein=f.has_weight&&n.has_protein,has_fat=f.has_weight&&n.has_fat};
    }
    public static string MacroText(VisionFood f)
    {
        float factor=f.has_weight?f.grams/100f:1;
        Func<float,bool,string> show=(v,has)=>has?(v*factor).ToString("0.0"):"—";
        var n=f.per100;
        return (f.has_weight?"":"100g 기준 · ")+show(n.calories,n.has_calories)+" kcal\n탄 "+show(n.carbs,n.has_carbs)+"g · 단 "+show(n.protein,n.has_protein)+"g · 지 "+show(n.fat,n.has_fat)+"g";
    }
    private void Edited(){changed=true;RenderCards();RenderBoxes();Status("수정했습니다. 결과 저장 버튼으로 JSON을 저장할 수 있습니다.");}
    private void RenderBoxes()
    {
        photo.texture=original;Clear(overlays);
        foreach(var f in analysis.foods)
        {
            var box=Rect("Box_"+f.id,overlays);
            box.anchorMin=new Vector2(f.bbox[0],1-f.bbox[3]);box.anchorMax=new Vector2(f.bbox[2],1-f.bbox[1]);box.offsetMin=box.offsetMax=Vector2.zero;
            for(int side=0;side<4;side++)
            {
                var edge=Rect("Edge",box);var img=edge.gameObject.AddComponent<Image>();img.color=new Color(0,.65f,.35f);img.raycastTarget=false;
                if(side<2){edge.anchorMin=new Vector2(0,side);edge.anchorMax=new Vector2(1,side);edge.sizeDelta=new Vector2(0,3);}
                else{edge.anchorMin=new Vector2(side-2,0);edge.anchorMax=new Vector2(side-2,1);edge.sizeDelta=new Vector2(3,0);}
                edge.anchoredPosition=Vector2.zero;
            }
            var label=Text(box,f.name,19,32);var r=label.rectTransform;
            r.anchorMin=new Vector2(0,1);r.anchorMax=new Vector2(1,1);r.pivot=new Vector2(0,1);r.offsetMin=new Vector2(0,-32);r.offsetMax=Vector2.zero;
            label.color=new Color(0,.4f,.15f);
        }
    }
    private void OpenNameDialog(VisionFood food)
    {
        if(busy)return;
        if(dialog!=null)Destroy(dialog.gameObject);
        dialog=Vertical("ChooseFood",transform);Stretch(dialog);dialog.SetAsLastSibling();
        dialog.gameObject.AddComponent<Image>().color=new Color(.97f,.98f,1);
        var lg=dialog.GetComponent<VerticalLayoutGroup>();lg.padding=new RectOffset(24,24,24,24);
        Text(dialog,"음식 변경 · CSV 음식명으로 검색",26,50);
        var row=Row(dialog,55);var query=Input(row,"","영문 음식명 (예: rice)",false);
        var choices=Scroll(dialog);
        Button(row,"검색",()=>StartCoroutine(Search(food,query.text,choices)));
        Button(dialog,"닫기",()=>Destroy(dialog.gameObject));
        StartCoroutine(Search(food,food.name,choices));
    }
    private IEnumerator Search(VisionFood food,string query,RectTransform choices)
    {
        if(busy)yield break;
        string url=BaseUrl();if(url==null)yield break;
        SetBusy(true);
        using(var request=UnityWebRequest.Get(url+"/vision/catalog?q="+UnityWebRequest.EscapeURL(query)))
        {
            activeRequest=request;request.timeout=20;yield return request.SendWebRequest();activeRequest=null;SetBusy(false);
            if(choices==null)yield break;
            Clear(choices);
            if(request.result!=UnityWebRequest.Result.Success){Text(choices,"검색 실패: "+request.error,22,60);yield break;}
            VisionCatalog list=null;
            try{list=JsonUtility.FromJson<VisionCatalog>(request.downloadHandler.text);}
            catch(Exception e){Status(e.Message);}
            if(list==null||list.items==null)yield break;
            if(list.items.Length==0)Text(choices,"검색 결과가 없습니다.",22,50);
            foreach(var item in list.items)
            {
                Button(choices,item.name,()=> {
                    food.class_id=item.class_id;food.name=item.name;food.per100=item.per100;
                    food.nutrition_source=item.nutrition_source;food.nutrition_confidence=item.nutrition_confidence;food.name_edited=true;
                    Destroy(dialog.gameObject);Edited();
                });
            }
        }
    }
    private void Save()
    {
        if(analysis==null){Status("먼저 사진을 분석하세요.");return;}
        try
        {
            // A server-rendered annotation is stale after edits. Save original + current boxes instead.
            var copy=JsonUtility.FromJson<VisionAnalysis>(JsonUtility.ToJson(analysis));
            if(changed)copy.annotated_base64="";
            string path=Path.Combine(Application.persistentDataPath,"food_analysis.json");
            File.WriteAllText(path,JsonUtility.ToJson(copy,true));Status("저장 완료: "+path);
        }
        catch(Exception e){Status("저장 실패: "+e.Message);}
    }
    private static void Clear(Transform parent){foreach(Transform child in parent){child.gameObject.SetActive(false);Destroy(child.gameObject);}}
    private static RectTransform Rect(string name,Transform parent){var o=new GameObject(name,typeof(RectTransform));o.transform.SetParent(parent,false);return o.GetComponent<RectTransform>();}
    private static void Stretch(RectTransform r){r.anchorMin=Vector2.zero;r.anchorMax=Vector2.one;r.offsetMin=r.offsetMax=Vector2.zero;}
    private static void Height(RectTransform r,float h){var e=r.gameObject.AddComponent<LayoutElement>();e.preferredHeight=h;e.minHeight=h;}
    private static void Width(RectTransform r,float w){var e=r.gameObject.AddComponent<LayoutElement>();e.preferredWidth=w;e.minWidth=w;}
    private RectTransform Vertical(string name,Transform parent)
    {
        var r=Rect(name,parent);var g=r.gameObject.AddComponent<VerticalLayoutGroup>();g.spacing=10;g.childControlHeight=true;g.childForceExpandHeight=false;
        return r;
    }
    private RectTransform Row(Transform parent,float h){var r=Rect("Row",parent);Height(r,h);var g=r.gameObject.AddComponent<HorizontalLayoutGroup>();g.spacing=8;g.childForceExpandWidth=true;return r;}
    private TMP_Text Text(Transform parent,string value,int size,float height)
    {
        var r=Rect("Text",parent);Height(r,height);var t=r.gameObject.AddComponent<TextMeshProUGUI>();t.font=font;t.text=value;t.fontSize=size;t.color=new Color(.1f,.15f,.2f);t.raycastTarget=false;t.enableWordWrapping=true;return t;
    }
    private Button Button(Transform parent,string label,UnityEngine.Events.UnityAction action,float width=0)
    {
        var r=Rect(label,parent);Height(r,52);if(width>0)r.GetComponent<LayoutElement>().preferredWidth=width;
        var image=r.gameObject.AddComponent<Image>();image.color=new Color(.84f,.92f,.9f);
        var b=r.gameObject.AddComponent<Button>();b.targetGraphic=image;b.onClick.AddListener(action);
        var text=Text(r,label,21,50);Stretch(text.rectTransform);text.alignment=TextAlignmentOptions.Center;return b;
    }
    private TMP_InputField Input(Transform parent,string value,string placeholder,bool number)
    {
        var r=Rect("Input",parent);Height(r,52);r.GetComponent<LayoutElement>().flexibleWidth=1;
        r.gameObject.AddComponent<Image>().color=Color.white;
        var field=r.gameObject.AddComponent<TMP_InputField>();var area=Rect("Area",r);Stretch(area);area.offsetMin=new Vector2(8,3);area.offsetMax=new Vector2(-8,-3);
        field.textViewport=area;var text=Text(area,"",21,45);Stretch(text.rectTransform);field.textComponent=(TMP_Text)text;
        var hint=Text(area,placeholder,19,45);Stretch(hint.rectTransform);hint.color=Color.gray;field.placeholder=hint;
        if(number)field.contentType=TMP_InputField.ContentType.DecimalNumber;
        field.text=value;return field;
    }
    private RectTransform Scroll(Transform parent)
    {
        var r=Rect("Scroll",parent);var e=r.gameObject.AddComponent<LayoutElement>();e.flexibleHeight=1;e.minHeight=100;
        var scroll=r.gameObject.AddComponent<ScrollRect>();scroll.horizontal=false;
        var viewport=Rect("Viewport",r);Stretch(viewport);viewport.gameObject.AddComponent<Image>().color=Color.clear;viewport.gameObject.AddComponent<RectMask2D>();
        var body=Vertical("Content",viewport);body.anchorMin=new Vector2(0,1);body.anchorMax=Vector2.one;body.pivot=new Vector2(.5f,1);body.offsetMin=body.offsetMax=Vector2.zero;
        body.gameObject.AddComponent<ContentSizeFitter>().verticalFit=ContentSizeFitter.FitMode.PreferredSize;
        scroll.viewport=viewport;scroll.content=body;return body;
    }
}
