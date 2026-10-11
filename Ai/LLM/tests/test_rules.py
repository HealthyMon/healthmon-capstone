from datetime import datetime,timedelta,timezone
from src.rules import replay,role_intent

def message(i,at,text,session='a'):
    return {'id':str(i),'kind':'message','revision':1,'occurred_at':at,'session_id':session,'payload':{'text':text},'valid':True}

def test_no_change_and_time_decay():
    at=datetime(2026,9,28,tzinfo=timezone.utc)
    result=replay([message(1,at,'안녕')],now=at)
    assert result['traits']['initiative']==50 and not result['history']
    tired=[message(2,at,'피곤해')]
    a=replay(tired,now=at);b=replay(tired,now=at+timedelta(minutes=30))
    assert b['mood']['valence']==a['mood']['valence']/2
    assert replay(tired,now=at)==a

def test_independent_evidence_sessions_and_deletion():
    at=datetime(2026,9,27,tzinfo=timezone.utc)
    texts=['ㅋㅋ 오늘 날개로 인사해','장난으로 배를 미끄럼틀 삼자','안녕','농담 하나 들려주고 싶어','잘 자']
    rows=[message(i,at+timedelta(minutes=i),texts[i],'a' if i<3 else 'b') for i in range(5)]
    assert replay(rows,now=at+timedelta(hours=1))['traits']['playfulness']==51
    rows[0]['valid']=False
    assert replay(rows,now=at+timedelta(hours=1))['traits']['playfulness']==50
    for row in rows: row['valid']=True;row['payload']['text']='ㅋㅋ 똑같은 말'
    assert replay(rows,now=at+timedelta(hours=1))['traits']['playfulness']==50

def test_daily_limit_and_two_sessions():
    at=datetime(2026,9,27,tzinfo=timezone.utc)
    phrases=['날개로 악수하자','빙산으로 이사할까','생선 택배 왔어','꼬리를 흔들어','눈사람이 도망가','라면 먹는 북극곰','동그란 달이 떴네','바람에 모자가 날아가','연필은 무슨 꿈을 꿀까','이불 밖이 무서워','물고기는 자전거를 탈까','수박을 우주에 보내자','비 오는 날 탭댄스','신발이 커피를 마셔','의자와 소파의 대결']
    rows=[message(i,at+timedelta(minutes=i),'농담 '+phrases[i//3] if i%3==0 else ('ㅋㅋ '+phrases[(i//3+5)%15] if i%3==1 else '장난 '+phrases[(i//3+10)%15]),str(i//3)) for i in range(45)]
    state=replay(rows,now=at+timedelta(hours=2))
    assert state['traits']['playfulness']<=55
    assert sum(abs(x['delta']) for x in state['history'])<=5
    for row in rows:row['session_id']='same'
    assert replay(rows,now=at+timedelta(hours=2))['traits']['playfulness']==50

def test_role_boundary():
    for text in ['과제 때문에 힘들어','운동 대신 스트레칭해도 돼?','운동 루틴 추천해줘']:
        assert role_intent(text)=='normal'
    for text in ['과제 코드 전체 대신 만들어줘','보고서 완성본 대신 써줘','리포트를 제출할 수 있게 작성해줘']:
        assert role_intent(text)=='assignment'

def test_repeated_evidence_is_not_reused_across_reviews(monkeypatch):
    from src.rules import RULES,tags
    at=datetime(2026,9,27,tzinfo=timezone.utc)
    phrases=['농담인데 날개로 악수하자','ㅋㅋ 물고기 택배가 도착했대','장난으로 빙산을 침대로 삼자','안녕','날이 맑아']
    rows=[message(i,at+timedelta(minutes=i),phrases[i%5],str(i//2)) for i in range(30)]
    assert replay(rows,now=at+timedelta(hours=1))['traits']['playfulness']==51
    monkeypatch.setitem(RULES,'daily_absolute_limit',0)
    assert replay(rows,now=at+timedelta(hours=1))['traits']['playfulness']==50
    assert not tags('피곤하지 않아요')['tired']
