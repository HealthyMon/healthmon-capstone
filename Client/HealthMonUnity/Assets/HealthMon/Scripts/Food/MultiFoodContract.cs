using System;
using System.Collections.Generic;

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

public static class MultiFoodContract
{
    public static void Validate(VisionAnalysis value)
    {
        if(value == null || value.schema_version != 1 || value.image_width <= 0 || value.image_height <= 0 ||
           (long)value.image_width * value.image_height > 16000000 || value.foods == null || value.foods.Length < 1 || value.foods.Length > 32)
            throw new FormatException("음식 분석 응답 형식 오류");
        var ids = new HashSet<int>();
        foreach(var f in value.foods)
        {
            if(f == null || f.id < 0 || !ids.Add(f.id) || f.class_id < 0 || f.class_id >= 2000 ||
               string.IsNullOrWhiteSpace(f.name) || f.bbox == null || f.bbox.Length != 4 || f.per100 == null)
                throw new FormatException("음식 정보 누락");
            foreach(float x in f.bbox) if(!Bounded(x, 0, 1)) throw new FormatException("음식 좌표 오류");
            if(f.bbox[0] >= f.bbox[2] || f.bbox[1] >= f.bbox[3] || !Bounded(f.name_confidence, 0, 1) ||
               !Bounded(f.grams, 0, 10000) || (f.has_weight && f.grams <= 0)) throw new FormatException("음식 수치 오류");
            foreach(float n in new[]{f.per100.calories, f.per100.carbs, f.per100.protein, f.per100.fat})
                if(!Bounded(n, 0, float.MaxValue)) throw new FormatException("영양소 수치 오류");
        }
    }
    private static bool Bounded(float x,float low,float high) => !float.IsNaN(x) && !float.IsInfinity(x) && x >= low && x <= high;
    public static void Recalculate(VisionFood f)
    {
        float ratio = f.has_weight ? f.grams / 100f : 0;
        var n = f.per100;
        f.nutrients = new VisionNutrients { calories=n.calories*ratio, carbs=n.carbs*ratio, protein=n.protein*ratio, fat=n.fat*ratio,
            has_calories=f.has_weight&&n.has_calories, has_carbs=f.has_weight&&n.has_carbs,
            has_protein=f.has_weight&&n.has_protein, has_fat=f.has_weight&&n.has_fat };
    }
}
