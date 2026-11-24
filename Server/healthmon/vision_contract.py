"""Bounded multi-food response shared by the API and authenticated AI bridge."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class VisionNutrients(Strict):
    calories: float = Field(ge=0)
    carbs: float = Field(ge=0)
    protein: float = Field(ge=0)
    fat: float = Field(ge=0)
    has_calories: bool
    has_carbs: bool
    has_protein: bool
    has_fat: bool


class VisionFood(Strict):
    id: int = Field(ge=0)
    class_id: int = Field(ge=0, lt=2000)
    name: str = Field(min_length=1, max_length=200)
    grams: float = Field(ge=0, le=10000)
    has_weight: bool
    weight_status: str = Field(max_length=100)
    name_confidence: float = Field(ge=0, le=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    per100: VisionNutrients
    crop_base64: str = Field(max_length=100000)
    nutrition_source: str = Field(max_length=300)
    nutrition_confidence: str = Field(max_length=100)
    name_edited: bool = False
    weight_edited: bool = False

    @model_validator(mode='after')
    def valid_region(self):
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError('Invalid normalized food region')
        if self.has_weight and self.grams <= 0:
            raise ValueError('A reported weight must be positive')
        return self


class VisionAnalysis(Strict):
    schema_version: int = Field(ge=1, le=1)
    analysis_id: str = Field(min_length=1, max_length=100)
    image_width: int = Field(gt=0, le=16000000)
    image_height: int = Field(gt=0, le=16000000)
    original_base64: str = Field(max_length=1000000)
    annotated_base64: str = Field(default='', max_length=1000000)
    foods: list[VisionFood] = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def unique_regions(self):
        if len({f.id for f in self.foods}) != len(self.foods):
            raise ValueError('Food region IDs must be unique')
        if self.image_width * self.image_height > 16000000:
            raise ValueError('Food image exceeds the pixel limit')
        return self
