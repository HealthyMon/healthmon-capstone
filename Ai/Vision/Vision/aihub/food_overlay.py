"""Draw food names only; Unity consumes all other details from result.json."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def wrap(draw, text, font, width):
    lines, line = [], ''
    for character in text:
        if character == '\n' or (line and draw.textlength(line + character, font=font) > width):
            lines.append(line)
            line = '' if character == '\n' else character
        else:
            line += character
    if line:
        lines.append(line)
    return lines


def render(payload, image, directory):
    directory = Path(directory)
    size = max(14, min(26, image.width // 40))
    font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', size)
    line_height = size + 7
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    colors = ['#086b56', '#1557a0', '#83409b', '#a24519', '#6b6310']
    cards = []
    for food in payload['foods']:
        color = colors[food['id'] % len(colors)]
        box = food['bbox_xyxy']
        title = food['name']
        lines = wrap(draw, title, font, max(50, min(340, image.width - 8)))
        width = min(image.width, int(max(draw.textlength(s, font=font) for s in lines)) + 8)
        height = len(lines) * line_height + 4
        x = max(0, min(int(box[0]), image.width - width))
        y = max(0, min(int(box[1]) - height, image.height - height))
        draw.rectangle(box, outline=color, width=max(2, image.width // 300))
        draw.rectangle((x, y, x + width, y + height), fill=color)
        for index, text in enumerate(lines):
            draw.text((x+4, y+2+index*line_height), text, font=font, fill='white')
        nutrition = food.get('nutrition') or {}
        per100 = nutrition.get('per_100g',{})
        portion = nutrition.get('portion')
        def value(values,key,unit):
            amount = values.get(key)
            return '자료 없음' if amount is None else f'{amount:.1f} {unit}'
        details = [f"{food['id']+1}. {food['name']}",
                   '중량: ' + ('산출 안 됨' if food.get('weight_g') is None else f"{food['weight_g']:.1f} g"),
                   '100g 기준',
                   '열량 '+value(per100,'energy_kcal_100g','kcal'),
                   '탄수화물 '+value(per100,'carbohydrate_g_100g','g')+' · 단백질 '+value(per100,'protein_g_100g','g'),
                   '지방 '+value(per100,'fat_g_100g','g')]
        if portion:
            totals = portion['values']
            details.extend(['예측 중량 기준', '열량 '+value(totals,'energy_kcal','kcal'),
                            '탄수화물 '+value(totals,'carbohydrate_g','g')+' · 단백질 '+value(totals,'protein_g','g'),
                            '지방 '+value(totals,'fat_g','g')])
        details.append(f"분류 점수 {food.get('name_confidence',0) or 0:.1%} · 위치 점수 {food['confidence']:.1%}")
        cards.append((color,[line for detail in details for line in wrap(draw,detail,font,450)],food))
    annotated.save(directory/'annotated.jpg', quality=95)
    panel_height = 65 + sum(max(len(lines)*line_height,100)+28 for _,lines,_ in cards)
    overview = Image.new('RGB',(image.width+610,max(image.height,panel_height)),'#f4f6f8')
    overview.paste(annotated,(0,0))
    panel = ImageDraw.Draw(overview)
    panel.text((image.width+16,12),'음식별 중량·영양소',font=font,fill='#152b36')
    y = 50
    if not cards:
        panel.text((image.width+16,y),'검출된 음식 없음',font=font,fill='#152b36')
    for color,lines,food in cards:
        height = max(len(lines)*line_height,100)
        panel.rectangle((image.width+10,y-4,image.width+600,y+height+8),fill='white',outline=color,width=2)
        crop = image.crop(tuple(map(int,food['bbox_xyxy'])))
        crop.thumbnail((100,100))
        overview.paste(crop,(image.width+18,y+4))
        for index,line in enumerate(lines):
            panel.text((image.width+130,y+index*line_height),line,font=font,fill='#152b36')
        y += height+28
    overview.save(directory/'overview.jpg', quality=95)
