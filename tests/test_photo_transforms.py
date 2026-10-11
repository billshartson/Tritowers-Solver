import random
import pytest
from tools import vision_synth as synth
from tritowers_vision.reader import read_photo


@pytest.mark.parametrize('degrees',[-5,5])
@pytest.mark.parametrize('removed',[0,27])
def test_rotation_and_scale_preserve_visible_tableau(degrees,removed):
    rng=random.Random(244+removed)
    deal=synth.random_deal(rng,removed)
    image=synth.render_screen(deal,synth.Skin(),rng).resize((1280,960)).rotate(degrees,expand=True,fillcolor='#202020')
    result=read_photo(image)
    assert result.registration.trusted,result.draft['registration']
    assert result.registration.present=={i for i,t in enumerate(deal.tableau,1) if t!='--'}
