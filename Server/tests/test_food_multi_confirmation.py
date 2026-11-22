import pytest


def prepare(client,pet,settings,monkeypatch):
    settings.ai_mode='remote'
    payload={'candidates':[{'food':'fixture','confidence':.9,'estimated_grams':100.,'per_100g':{'energy_kcal':100.,'carbohydrate_g':10.,'protein_g':5.,'fat_g':2.,'vegetable_fruit_g':None}}],
             'vision':{'foods':[{'id':1},{'id':2}]}}
    monkeypatch.setattr('Server.healthmon.app.Gateway.call',lambda *a,**k:(payload,'real'))
    monkeypatch.setattr('Server.healthmon.food_portions.catalog',lambda:{
        4:{'name':'rice','per100':{'calories':100.,'has_calories':True,'carbs':20.,'has_carbs':True,'protein':2.,'has_protein':True,'fat':1.,'has_fat':True}},
        9:{'name':'beans','per100':{'calories':200.,'has_calories':True,'carbs':10.,'has_carbs':True,'protein':10.,'has_protein':True,'fat':5.,'has_fat':True}}})
    response=client.post(f'/pets/{pet}/food/analyze',content=b'\x89PNG\r\n\x1a\nfixture',headers={'X-Request-Id':'multi-food-fixture','Content-Type':'image/png'})
    assert response.status_code==200,response.text
    return {'analysis_id':'multi-food-fixture','candidate_id':0,'grams':250.,'meal_type':'lunch',
            'items':[{'region_id':1,'class_id':4,'grams':100.},{'region_id':2,'class_id':9,'grams':150.}]}


def test_multi_food_saved_once_with_edited_names_weights(client,pet,settings,monkeypatch):
    body=prepare(client,pet,settings,monkeypatch)
    first=client.post(f'/pets/{pet}/food/confirm',json=body)
    assert first.status_code==200,first.text
    result=first.json()
    assert result['record']['food']=='rice, beans'
    assert result['record']['nutrition']['energy_kcal']['value']==400
    assert result['record']['nutrition']['protein_g']['value']==17
    assert len(result['record']['items'])==2
    again=client.post(f'/pets/{pet}/food/confirm',json=body)
    assert again.status_code==200 and again.json()['duplicate']
    assert again.json()['state']['total_exp']==result['state']['total_exp']
    records=client.get(f'/pets/{pet}/meals').json()['records']
    assert len(records)==1 and len(records[0]['record']['food_items'])==2


@pytest.mark.parametrize('issue',['duplicate','missing','unknown','total','unconfirmed'])
def test_reject_invalid_portions(client,pet,settings,monkeypatch,issue):
    body=prepare(client,pet,settings,monkeypatch)
    if issue=='duplicate':body['items'][1]['region_id']=1
    if issue=='missing':body['items'].pop()
    if issue=='unknown':body['items'][0]['class_id']=99999
    if issue=='total':body['grams']=99
    if issue=='unconfirmed':body.pop('grams')
    response=client.post(f'/pets/{pet}/food/confirm',json=body)
    assert response.status_code==422,response.text
    assert not client.get(f'/pets/{pet}/meals').json()['records']
