"""Tests du volet vision : redressement EXIF des photos et remise a l'echelle des boites.

Ces deux mecanismes echouent silencieusement s'ils sont faux — une photo couchee reste une image
valide, une boite decalee reste un rectangle. D'ou des tests sur des cas construits, ou la bonne
reponse est connue d'avance.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from rda.ra.images import PhotoInvalide, en_octets, normaliser, preparer, verifier_photo
from rda.ra.localisation import extraire_boites, facteurs_echelle, smart_resize

MIN_PIXELS = 256 * 28 * 28  # 200 704
MAX_PIXELS = 1024 * 28 * 28  # 802 816


# --------------------------------------------------------------------- smart_resize


def test_smart_resize_rend_des_multiples_du_facteur():
    hauteur, largeur = smart_resize(1200, 1600, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    assert hauteur % 28 == 0 and largeur % 28 == 0


def test_smart_resize_respecte_le_plafond_de_pixels():
    hauteur, largeur = smart_resize(3000, 4000, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    assert hauteur * largeur <= MAX_PIXELS


def test_smart_resize_respecte_le_plancher_de_pixels():
    hauteur, largeur = smart_resize(100, 120, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    assert hauteur * largeur >= MIN_PIXELS


def test_smart_resize_preserve_le_rapport_d_aspect():
    hauteur, largeur = smart_resize(1200, 1600, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    assert largeur / hauteur == pytest.approx(1600 / 1200, rel=0.05)


def test_smart_resize_laisse_intacte_une_image_deja_conforme():
    """756 x 1008 est deja un multiple de 28 et dans les bornes : rien ne doit bouger."""
    assert smart_resize(756, 1008, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS) == (756, 1008)


def test_smart_resize_refuse_un_rapport_d_aspect_extreme():
    with pytest.raises(ValueError, match="rapport d'aspect"):
        smart_resize(10, 5000, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)


def test_smart_resize_refuse_des_dimensions_nulles():
    with pytest.raises(ValueError, match="dimensions invalides"):
        smart_resize(0, 100, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)


def test_les_facteurs_d_echelle_sont_egaux_sur_les_deux_axes():
    """Le rapport d'aspect etant preserve, fx et fy doivent coincider."""
    fx, fy = facteurs_echelle(1600, 1200, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    assert fx == pytest.approx(fy, rel=0.02)
    assert fx > 1  # la photo est plus grande que ce que voit le modele


# --------------------------------------------------------------------- extraction des boites


def _extraire(brut: str, largeur: int = 1600, hauteur: int = 1200):
    return extraire_boites(
        brut,
        cible="roulement",
        largeur_photo=largeur,
        hauteur_photo=hauteur,
        min_pixels=MIN_PIXELS,
        max_pixels=MAX_PIXELS,
    )


def test_une_boite_est_ramenee_aux_pixels_de_la_photo():
    """Le modele voit 1008 x 756 ; une boite pleine cadre doit ressortir en 1600 x 1200."""
    boites = _extraire('[{"bbox_2d": [0, 0, 1008, 756], "label": "roulement"}]')
    assert len(boites) == 1
    x1, y1, x2, y2 = boites[0]["bbox"]
    assert (x1, y1) == (0, 0)
    assert x2 == pytest.approx(1600, abs=2) and y2 == pytest.approx(1200, abs=2)


def test_la_boite_est_bornee_aux_dimensions_de_la_photo():
    boites = _extraire('[{"bbox_2d": [-50, -50, 99999, 99999], "label": "x"}]')
    assert boites[0]["bbox"] == [0, 0, 1600, 1200]


def test_les_coins_inverses_sont_remis_dans_l_ordre():
    boites = _extraire('[{"bbox_2d": [500, 400, 100, 50], "label": "x"}]')
    x1, y1, x2, y2 = boites[0]["bbox"]
    assert x1 < x2 and y1 < y2


def test_liste_vide_quand_le_modele_ne_trouve_rien():
    assert _extraire("[]") == []


def test_liste_vide_sur_une_sortie_sans_json():
    assert _extraire("Je ne vois pas cet element dans l'image.") == []


def test_liste_vide_sur_un_json_malforme():
    """Un JSON casse ne doit jamais devenir une boite dessinee sur la photo du technicien."""
    assert _extraire('[{"bbox_2d": [10, 20, ') == []


def test_les_virgules_trainantes_sont_reparees():
    boites = _extraire('[{"bbox_2d": [10, 20, 300, 400], "label": "x",},]')
    assert len(boites) == 1


def test_une_boite_degeneree_est_ecartee():
    """Apres bornage, une boite de surface nulle n'a rien a dessiner."""
    assert _extraire('[{"bbox_2d": [100, 100, 100, 100], "label": "x"}]') == []


def test_le_libelle_par_defaut_est_la_cible():
    boites = _extraire('[{"bbox_2d": [10, 20, 300, 400]}]')
    assert boites[0]["label"] == "roulement"


def test_les_entrees_invalides_sont_ignorees_sans_faire_echouer_les_autres():
    boites = _extraire(
        '[{"bbox_2d": [1, 2]}, "texte", {"bbox_2d": [10, 20, 300, 400], "label": "bon"}]'
    )
    assert len(boites) == 1 and boites[0]["label"] == "bon"


# --------------------------------------------------------------------- photos et EXIF


def _jpeg(largeur: int, hauteur: int, orientation: int | None = None) -> bytes:
    image = Image.new("RGB", (largeur, hauteur), (200, 30, 40))
    tampon = io.BytesIO()
    if orientation is None:
        image.save(tampon, format="JPEG")
    else:
        exif = image.getexif()
        exif[0x0112] = orientation  # etiquette Orientation
        image.save(tampon, format="JPEG", exif=exif)
    return tampon.getvalue()


def test_une_photo_portrait_avec_exif_est_redressee():
    """Orientation 6 : le capteur a ecrit l'image couchee, il faut pivoter de 90 degres.

    Sans redressement, une photo prise en portrait serait encodee en paysage et la similarite
    visuelle s'effondrerait.
    """
    image = normaliser(_jpeg(800, 600, orientation=6), max_cote=0)
    assert image.size == (600, 800)


def test_une_photo_sans_exif_garde_ses_dimensions():
    assert normaliser(_jpeg(800, 600), max_cote=0).size == (800, 600)


def test_le_grand_cote_est_reduit():
    assert max(normaliser(_jpeg(3000, 2000), max_cote=1600).size) == 1600


def test_la_conversion_en_rgb_est_systematique():
    tampon = io.BytesIO()
    Image.new("L", (100, 100), 128).save(tampon, format="PNG")
    assert normaliser(tampon.getvalue()).mode == "RGB"


def test_une_photo_vide_est_refusee():
    with pytest.raises(PhotoInvalide, match="vide"):
        verifier_photo(b"", "image/jpeg")


def test_un_format_non_pris_en_charge_est_refuse():
    with pytest.raises(PhotoInvalide, match="Format"):
        verifier_photo(b"GIF89a", "image/gif")


def test_le_type_mime_avec_parametres_est_accepte():
    verifier_photo(_jpeg(10, 10), "image/jpeg; charset=binary")


def test_une_photo_trop_lourde_est_refusee():
    from rda.ra.config import obtenir_parametres_ra

    trop = b"\xff" * (obtenir_parametres_ra().taille_max_photo_octets + 1)
    with pytest.raises(PhotoInvalide, match="Mo"):
        verifier_photo(trop, "image/jpeg")


def test_une_image_corrompue_est_refusee():
    with pytest.raises(PhotoInvalide, match="illisible"):
        normaliser(b"ceci n'est pas une image")


def test_preparer_rend_une_image_et_son_jpeg():
    image, octets = preparer(_jpeg(400, 300), "image/jpeg")
    assert image.size == (400, 300)
    assert octets.startswith(b"\xff\xd8")  # en-tete JPEG


def test_en_octets_produit_un_jpeg_relisible():
    image = Image.new("RGB", (50, 40), (1, 2, 3))
    assert Image.open(io.BytesIO(en_octets(image))).size == (50, 40)
