"""Public fixtures exercise phone normalization; owner captures stay local."""
from io import BytesIO
from pathlib import Path
import os
import numpy as np
import pytest
from PIL import Image
from tritowers_vision.image import normalize_image, ImageInputError, MAX_SIDE


def encoded(image, fmt='JPEG', **kwargs):
    out=BytesIO();image.save(out,fmt,**kwargs);return out.getvalue()


@pytest.mark.parametrize('orientation',[1,2,3,4,5,6,7,8])
def test_exif_orientation_applied_once(orientation):
    im=Image.new('RGB',(240,180),'white')
    im.paste('red',(0,0,90,70));exif=Image.Exif();exif[274]=orientation
    got=normalize_image(encoded(im,exif=exif))
    from PIL import ImageOps
    expected=ImageOps.exif_transpose(Image.open(BytesIO(encoded(im,exif=exif)))).convert('RGB')
    assert got.size==expected.size
    assert np.array_equal(np.array(got),np.array(expected))
    assert normalize_image(got).size==got.size
    assert got.getexif().get(274) in (None,1)


def test_48mp_jpeg_reduced_before_array_allocation():
    data=encoded(Image.new('RGB',(8064,6048),'beige'))
    got=normalize_image(data)
    assert got.size==(1600,1200)
    assert np.asarray(got).nbytes<=MAX_SIDE*MAX_SIDE*3


@pytest.mark.parametrize('data',[b'not an image',b'',b'\xff\xd8broken'])
def test_failed_decode_is_actionable(data):
    with pytest.raises(ImageInputError,match='decode'):normalize_image(data)


def test_unsupported_image():
    with pytest.raises(ImageInputError,match='Unsupported'):normalize_image(encoded(Image.new('RGB',(200,200)),'GIF'))


def test_pil_input_also_bounded_without_mutating_source():
    source=Image.new('RGB',(3200,2400));got=normalize_image(source)
    assert got.size==(1600,1200) and source.size==(3200,2400)


def test_heic_decodes_and_orients():
    import pillow_heif
    original=Image.new('RGB',(320,240),'red')
    data=BytesIO();pillow_heif.from_pillow(original).save(data,quality=90)
    got=normalize_image(data.getvalue())
    assert got.size==(320,240) and np.array(got)[100,100,0]>200


@pytest.mark.skipif(not os.getenv('TT_PRIVATE_PHOTOS'),reason='private iPhone captures not supplied')
def test_actual_iphone_heic_and_jpeg():
    photos=list(Path(os.environ['TT_PRIVATE_PHOTOS']).glob('*.HEIC'))+list(Path(os.environ['TT_PRIVATE_PHOTOS']).glob('*.JPG'))
    assert any(p.suffix=='.HEIC' for p in photos) and any(p.suffix=='.JPG' for p in photos)
    for photo in photos:
        image=normalize_image(photo)
        assert image.mode=='RGB' and max(image.size)<=1600
