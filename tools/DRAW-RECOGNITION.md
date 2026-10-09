# Guided draw-screen rank prototype

Source-only object detector, paired glyph extraction and rank proposal matcher for a full draw screen. Callers supply a BGR uint8 image, row guides, expected row counts and a privately curated paired template bank. No photo, guide, glyph or template data is bundled.

This is separate from the existing 28-tableau photo reader. It does not replace that reader, change the UI or provide accepted solver input. Every match returns rank=null, accepted=false and needs_visual_review=true. Blank, constant and nonfinite query views abstain. Count, spacing and endpoint checks reject inconsistent geometry; passing them never makes a rank safe.

25 synthetic tests cover detection, extraction, geometry and draft boundaries. Private research reached 208/208 rank proposals with other-photo templates from 191 visually complete crops on the same four tuning photos. Normalization, geometry and matcher choices were tuned on that set, so this is not independent performance. Manual row guides remain required. Negative tests rejected all 208 individually masked ranks on that same set; this is not a general safety guarantee.

Nothing is deployed. Private images, crops, manifests and evaluation harnesses must stay outside the repository.
