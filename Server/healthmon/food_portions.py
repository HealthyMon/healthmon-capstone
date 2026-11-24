"""Resolve edited region selections using the server-owned nutrition catalog."""
import json
import math
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException

@lru_cache(maxsize=1)
def catalog():
    rows=json.loads((Path(__file__).parent/'data/food_catalog.json').read_text(encoding='utf-8'))['items']
    return {row['class_id']:row for row in rows}

def resolve_items(analysis, items, total_grams):
    regions={food['id'] for food in (analysis.get('vision') or {}).get('foods',[])}
    if not regions:raise HTTPException(422,'This analysis has no food regions')
    ids=[item.region_id for item in items]
    if len(ids)!=len(set(ids)) or set(ids)!=regions:raise HTTPException(422,'Confirm each detected region exactly once')
    total=sum(item.grams for item in items)
    if total_grams is None or total>10000 or not math.isclose(total,total_grams,abs_tol=.05):
        raise HTTPException(422,'Confirmed total must match the food quantities')
    nutrients={key:0.0 for key in ('energy_kcal','carbohydrate_g','protein_g','fat_g')}
    rows=[]
    for item in items:
        entry=catalog().get(item.class_id)
        if entry is None:raise HTTPException(422,'Unknown food class')
        portion={}
        for key,source in [('energy_kcal','calories'),('carbohydrate_g','carbs'),('protein_g','protein'),('fat_g','fat')]:
            n=entry['per100'];value=n[source]*item.grams/100 if n.get('has_'+source) else None
            portion[key]=value
            nutrients[key]=None if value is None or nutrients[key] is None else nutrients[key]+value
        rows.append(dict(region_id=item.region_id,class_id=item.class_id,food=entry['name'],grams=item.grams,nutrition=portion))
    name=', '.join(row['food'] for row in rows)
    if len(name)>200:name=name[:197]+'...'
    return name,nutrients,rows
