using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using Healthmon.Beta;

// Created only by MainARScene's result view. Uses its existing authenticated response.
public sealed class MainFoodResultsPanel : MonoBehaviour
{
    TMP_FontAsset font;
    RectTransform cards, editor, photoFrame;
    TMP_Text feedback;
    VisionAnalysis analysis;
    VisionCatalog catalog;
    readonly List<Texture2D> textures = new List<Texture2D>();
    public bool HasEdits { get; private set; }
    public event Action PortionsChanged;
    public bool HasPortions => analysis != null && analysis.foods != null && analysis.foods.Length > 0 && analysis.image_width > 0;
    public float TotalGrams {
        get { float total=0; if(!HasPortions)return 0; foreach(var f in analysis.foods){if(!f.has_weight||float.IsNaN(f.grams)||float.IsInfinity(f.grams)||f.grams<=0)return 0; total+=f.grams;} return total; }
    }
    public ConfirmedFoodItem[] ConfirmedItems() {
        if(!HasPortions || TotalGrams<=0 || TotalGrams>10000)throw new ArgumentException("음식별 중량을 확인해 주세요. 합계는 10,000g 이하여야 합니다.");
        var items=new List<ConfirmedFoodItem>();
        foreach(var f in analysis.foods)items.Add(new ConfirmedFoodItem{region_id=f.id,class_id=f.class_id,grams=f.grams});
        return items.ToArray();
    }

    public void Initialize(TMP_FontAsset value)
    {
        font=value;
        var layout=gameObject.AddComponent<VerticalLayoutGroup>();
        layout.spacing=14;layout.childControlWidth=true;layout.childControlHeight=true;
        layout.childForceExpandWidth=true;layout.childForceExpandHeight=false;
        Label(transform,"전체 음식 사진 · 음식별 분석",30,55);
        photoFrame=Box("WholePhoto",transform,390);
        feedback=Label(transform,"사진 분석 후 음식별 결과가 표시됩니다.",22,70);
        cards=Box("FoodCards",transform,0); Vertical(cards);
        Button(transform,"수정 결과 JSON 저장",Save);
        var asset=Resources.Load<TextAsset>("MainFoodCatalog");
        if(asset!=null)catalog=JsonUtility.FromJson<VisionCatalog>(asset.text);
    }
    public void Show(FoodAnalysis result,byte[] photo)
    {
        HasEdits=false;Clear(cards);Clear(photoFrame);CloseEditor();
        foreach(var t in textures)if(t!=null)Destroy(t);textures.Clear();
        if(result.vision!=null)
        {
            try{MultiFoodScanPanel.Validate(result.vision);analysis=JsonUtility.FromJson<VisionAnalysis>(JsonUtility.ToJson(result.vision));}
            catch(Exception e){analysis=null;feedback.text="전체 음식 응답 오류: "+e.Message;return;}
        }
        else
        {
            var foods=new List<VisionFood>();
            foreach(var c in result.candidates??new FoodCandidate[0])foods.Add(new VisionFood{
                id=c.candidate_id,name=c.food,grams=c.estimated_grams,has_weight=c.has_estimated_grams,
                bbox=new float[]{0,0,1,1},per100=new VisionNutrients{
                    calories=Value(c.per_100g.energy_kcal),has_calories=Available(c.per_100g.energy_kcal),
                    carbs=Value(c.per_100g.carbohydrate_g),has_carbs=Available(c.per_100g.carbohydrate_g),
                    protein=Value(c.per_100g.protein_g),has_protein=Available(c.per_100g.protein_g),
                    fat=Value(c.per_100g.fat_g),has_fat=Available(c.per_100g.fat_g)}});
            analysis=new VisionAnalysis{schema_version=1,analysis_id=result.analysis_id,foods=foods.ToArray()};
        }
        analysis.analysis_id=result.analysis_id;
        byte[] original=photo;
        if(!string.IsNullOrEmpty(analysis.original_base64))original=Convert.FromBase64String(analysis.original_base64);
        if(original!=null)analysis.original_base64=Convert.ToBase64String(original);
        byte[] display=original;
        if(!string.IsNullOrEmpty(analysis.annotated_base64))display=Convert.FromBase64String(analysis.annotated_base64);
        if(display!=null)Picture(photoFrame,display);
        feedback.text=result.vision==null?"이 서버는 전체 검출 정보를 보내지 않습니다. 아래는 기존 후보 결과입니다.":"음식별 사진 추정량 기준입니다. 이름·중량 수정 시 영양소를 다시 계산합니다.";
        RenderCards();
    }
    static bool Available(NutrientValue n)=>n!=null&&n.available;
    static float Value(NutrientValue n)=>Available(n)?n.value:0;
    void RenderCards()
    {
        Clear(cards);
        if(analysis==null)return;
        foreach(var f in analysis.foods)
        {
            var card=Box("Food_"+f.id,cards,0);Vertical(card);
            card.gameObject.AddComponent<Image>().color=new Color(.12f,.18f,.22f,.9f);
            var group=card.GetComponent<VerticalLayoutGroup>();group.padding=new RectOffset(18,18,16,16);
            Label(card,f.name,28,65);
            if(!string.IsNullOrEmpty(f.crop_base64))
            {
                var crop=Box("Crop",card,170);
                try{Picture(crop,Convert.FromBase64String(f.crop_base64));}catch(FormatException){Label(crop,"사진을 읽지 못했습니다.",20,50);}
            }
            Label(card,"중량  "+(f.has_weight?f.grams.ToString("0.#")+" g":"정보 없음"),26,48);
            MultiFoodScanPanel.Recalculate(f);var n=f.nutrients;
            Label(card,"열량  "+Number(n.calories,n.has_calories," kcal"),28,50);
            Label(card,"탄수화물  "+Number(n.carbs,n.has_carbs," g")+"\n단백질  "+Number(n.protein,n.has_protein," g")+"\n지방  "+Number(n.fat,n.has_fat," g"),24,115);
            var actions=Box("FoodActions",card,76);
            var row=actions.gameObject.AddComponent<HorizontalLayoutGroup>();
            row.spacing=8;row.childControlWidth=row.childControlHeight=true;
            row.childForceExpandWidth=true;row.childForceExpandHeight=true;
            Button(actions,"음식이름\n재설정",()=>EditName(f,card));
            Button(actions,"중량\n재설정",()=>EditWeight(f,card));
            Button(actions,"기준중량으로\n변경",()=>UseReferenceWeight(f));
        }
    }
    void UseReferenceWeight(VisionFood food)
    {
        var item=Array.Find(catalog?.items??new VisionCatalogItem[0], x=>x.class_id==food.class_id);
        float grams=item==null?0:item.typical_serving_weight_g;
        if(float.IsNaN(grams)||float.IsInfinity(grams)||grams<=0||grams>10000)
        {feedback.text="이 음식의 기준중량 정보가 없습니다.";return;}
        food.grams=grams;food.has_weight=true;food.weight_edited=true;
        food.weight_status="reference_serving_weight";
        Changed();
        feedback.text=food.name+" 기준중량 "+grams.ToString("0.#")+" g을 적용했습니다. 열량과 탄단지도 갱신했습니다.";
    }
    void EditWeight(VisionFood food,RectTransform card)
    {
        CloseEditor();editor=Box("WeightEditor",card,0);Vertical(editor);
        Label(editor,"중량(g)을 입력하세요",22,45);
        var field=Input(editor,food.has_weight?food.grams.ToString("0.#",CultureInfo.InvariantCulture):"",true);
        Button(editor,"적용",()=>{
            if(!float.TryParse(field.text,NumberStyles.Float,CultureInfo.InvariantCulture,out float grams)||float.IsNaN(grams)||float.IsInfinity(grams)||grams<=0||grams>10000)
            {feedback.text="중량은 0보다 크고 10,000g 이하로 입력하세요.";return;}
            food.grams=grams;food.has_weight=true;food.weight_edited=true;Changed();
        });
        Button(editor,"취소",CloseEditor);
    }
    void EditName(VisionFood food,RectTransform card)
    {
        CloseEditor();editor=Box("NameEditor",card,0);Vertical(editor);
        Label(editor,"등록된 영문 음식명 검색 (예: rice)",22,50);
        var query=Input(editor,"",false);
        var choices=Box("Matches",editor,0);Vertical(choices);
        Button(editor,"검색",()=>{
            Clear(choices);int count=0;
            foreach(var item in catalog?.items??new VisionCatalogItem[0])
            {
                if(item.name.IndexOf(query.text.Trim(),StringComparison.OrdinalIgnoreCase)<0)continue;
                var match=item;
                Button(choices,match.name,()=>{food.name=match.name;food.class_id=match.class_id;
                    food.per100=match.per100;food.nutrition_source=match.nutrition_source;food.name_edited=true;Changed();});
                if(++count>=15)break;
            }
            if(count==0)Label(choices,"검색 결과가 없습니다.",22,50);
        });
        Button(editor,"취소",CloseEditor);
    }
    void Changed()
    {
        HasEdits=true;analysis.annotated_base64="";CloseEditor();
        // Crop textures are regenerated with the cards; retain only the whole-photo texture.
        for(int i=textures.Count-1;i>=1;i--){Destroy(textures[i]);textures.RemoveAt(i);}
        RenderCards();PortionsChanged?.Invoke();feedback.text="수정 완료. 실제 먹은 양을 확인 체크한 뒤 기록하기를 누르면 모든 음식이 한 식사로 저장됩니다.";
    }
    void Save()
    {
        if(analysis==null){feedback.text="먼저 분석해 주세요.";return;}
        try{string path=Path.Combine(Application.persistentDataPath,"main_food_analysis.json");File.WriteAllText(path,JsonUtility.ToJson(analysis,true));feedback.text="JSON 저장 완료: "+path;}
        catch(Exception e){feedback.text="저장 실패: "+e.Message;}
    }
    void CloseEditor(){if(editor!=null){editor.gameObject.SetActive(false);Destroy(editor.gameObject);editor=null;}}
    void Picture(RectTransform frame,byte[] bytes)
    {
        var t=new Texture2D(2,2);if(!t.LoadImage(bytes)){Destroy(t);return;}textures.Add(t);
        var image=Box("Image",frame,0);Stretch(image);
        var raw=image.gameObject.AddComponent<RawImage>();raw.texture=t;raw.raycastTarget=false;
        var fit=image.gameObject.AddComponent<AspectRatioFitter>();fit.aspectMode=AspectRatioFitter.AspectMode.FitInParent;fit.aspectRatio=(float)t.width/t.height;
    }
    TMP_InputField Input(Transform parent,string value,bool number)
    {
        var rect=Box("Input",parent,64);rect.gameObject.AddComponent<Image>().color=Color.white;
        var input=rect.gameObject.AddComponent<TMP_InputField>();var area=Box("TextArea",rect,0);Stretch(area);area.offsetMin=new Vector2(12,5);area.offsetMax=new Vector2(-12,-5);
        var label=Label(area,"",24,0);Stretch(label.rectTransform);label.color=Color.black;
        input.textViewport=area;input.textComponent=label;input.contentType=number?TMP_InputField.ContentType.DecimalNumber:TMP_InputField.ContentType.Standard;
        input.lineType=TMP_InputField.LineType.SingleLine;input.characterLimit=number?8:100;input.text=value;return input;
    }
    void Button(Transform parent,string text,UnityEngine.Events.UnityAction click)
    {
        var r=Box(text,parent,62);var image=r.gameObject.AddComponent<Image>();image.color=new Color(.18f,.43f,.36f);
        var button=r.gameObject.AddComponent<Button>();button.targetGraphic=image;button.onClick.AddListener(click);
        var label=Label(r,text,24,0);Stretch(label.rectTransform);label.alignment=TextAlignmentOptions.Center;
    }
    TMP_Text Label(Transform parent,string value,int size,float height)
    {
        var r=Box("Label",parent,height);var t=r.gameObject.AddComponent<TextMeshProUGUI>();t.font=font;t.text=value;t.fontSize=size;
        t.enableAutoSizing=true;t.fontSizeMin=18;t.fontSizeMax=size;t.color=Color.white;t.richText=false;t.raycastTarget=false;return t;
    }
    static string Number(float value,bool has,string unit)=>has?value.ToString("0.#")+unit:"정보 없음";
    static RectTransform Box(string name,Transform parent,float height)
    {
        var r=(RectTransform)new GameObject(name,typeof(RectTransform)).transform;r.SetParent(parent,false);
        if(height>0){var l=r.gameObject.AddComponent<LayoutElement>();l.minHeight=l.preferredHeight=height;}
        return r;
    }
    static void Vertical(RectTransform rect)
    {
        var l=rect.gameObject.AddComponent<VerticalLayoutGroup>();l.spacing=10;l.childControlHeight=l.childControlWidth=true;l.childForceExpandHeight=false;l.childForceExpandWidth=true;
    }
    static void Stretch(RectTransform r){r.anchorMin=Vector2.zero;r.anchorMax=Vector2.one;r.offsetMin=r.offsetMax=Vector2.zero;}
    static void Clear(Transform parent){foreach(Transform child in parent){child.gameObject.SetActive(false);Destroy(child.gameObject);}}
    void OnDestroy(){foreach(var t in textures)if(t!=null)Destroy(t);}
}
