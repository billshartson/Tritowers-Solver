from tools.vision_eval import score, summarise


def test_metrics_separate_wrong_names_abstention_and_presence():
    truth=['--','8','K','--']+['?']*24
    cards={'tableau-01':{'state':'face_up','rank':'2'},'tableau-02':{'state':'face_up','rank':None},'tableau-03':{'state':'empty','rank':None},'tableau-04':{'state':'unknown','rank':None},'waste':{'state':'face_up','rank':'3'}}
    scores,want=score({'cards':cards,'needs_human_review':['tableau-01']},truth,'2')
    report=summarise([(scores,want,.2)])
    assert report['wrong_named']==2  # flags do not conceal a wrong named rank
    assert report['rank_abstentions']==1
    assert report['false_present']==1 and report['false_empty']==1
    assert report['unknown_state']==25  # unknown geometry is distinct from an asserted presence
