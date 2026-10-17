"""Starting images: where each file comes from, its licence, alt text and where the seed places it.

Stock photos: Unsplash License (free commercial use, no attribution required; credit kept anyway).
Design renders: 3D visualisations from the mockups made with the "Car Concept" model by Eric Chadwick /
Darmstadt Graphics Group, CC BY 4.0 (attribution required, shown on /credits).
Every placement can be changed in the panel.
"""

from __future__ import annotations

UNSPLASH_LICENSE = "Unsplash License"
UNSPLASH_LICENSE_URL = "https://unsplash.com/license"
CC_BY = "CC BY 4.0"
CC_BY_URL = "https://creativecommons.org/licenses/by/4.0/"
CAR_CONCEPT_URL = "https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept"
CAR_CONCEPT_AUTHOR = "Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета"


def _unsplash(key: str, file: str, photo_id: str, author: str, username: str, alt: str) -> dict:
    return {
        "key": key,
        "file": f"stock/{file}",
        "alt": alt,
        "source_url": f"https://unsplash.com/photos/{photo_id}",
        "author": author,
        "author_url": f"https://unsplash.com/@{username}",
        "license": UNSPLASH_LICENSE,
        "license_url": UNSPLASH_LICENSE_URL,
        "is_example": False,
    }


def _render(key: str, file: str, alt: str) -> dict:
    return {
        "key": key,
        "file": f"design/{file}",
        "alt": alt,
        "source_url": CAR_CONCEPT_URL,
        "author": CAR_CONCEPT_AUTHOR,
        "author_url": None,
        "license": CC_BY,
        "license_url": CC_BY_URL,
        "is_example": True,
    }


MEDIA = [
    _unsplash(
        "stock_hero",
        "hero-sportscar-dark.jpg",
        "0xySZZ8OK1o",
        "Tuna Ekici",
        "tunaekici",
        "Чёрный спорткар в тёмном помещении, свет ложится бликами на кузов",
    ),
    _unsplash(
        "stock_hero_mobile",
        "hero-mobile-car-front.jpg",
        "HNCSCpWrVJA",
        "Ville Kaisla",
        "villekaisla",
        "Чёрный автомобиль анфас под потолочными лампами",
    ),
    _unsplash(
        "stock_final",
        "final-car-headlights.jpg",
        "ifC-l1kPLCs",
        "Graham Pengelly",
        "grahampengelly_",
        "Автомобиль анфас с включёнными фарами в тёмном помещении",
    ),
    _unsplash(
        "stock_polishing",
        "polishing-orbital-hood.jpg",
        "iXpjQNP__EQ",
        "Luay Barani",
        "luaybarani",
        "Мастер полирует капот орбитальной полировальной машинкой",
    ),
    _unsplash(
        "stock_ceramic",
        "ceramic-raindrops-car.jpg",
        "fi9zsbf3f5Y",
        "Tuomas Nylund",
        "tuomasnylund",
        "Капли воды на кузове тёмного автомобиля",
    ),
    _unsplash(
        "stock_droplets",
        "ceramic-water-droplets.jpg",
        "GqSVfquxyoo",
        "Christian Lue",
        "christianlue",
        "Капли воды на тёмной глянцевой поверхности",
    ),
    _unsplash(
        "stock_film_dark",
        "film-panel-peel-dark.jpg",
        "rsaYn6mq2qo",
        "Clarity Coat",
        "claritycoat",
        "Руки мастера в перчатках снимают защитное покрытие с панели кузова",
    ),
    _unsplash(
        "stock_film_blue",
        "film-panel-peel-blue.jpg",
        "G6sI_6B_FFY",
        "Clarity Coat",
        "claritycoat",
        "Мастер в перчатках снимает защитное покрытие с голубой панели",
    ),
    _unsplash(
        "stock_interior",
        "interior-cognac-leather.jpg",
        "T9CSi3hKV7Q",
        "Pheng Moua",
        "phengmua",
        "Салон с сиденьями из коньячной кожи",
    ),
    _unsplash(
        "stock_profile",
        "complex-sedan-profile.jpg",
        "FMbWFDiVRPs",
        "Samuele Errico Piccarini",
        "samuele_piccarini",
        "Чёрный седан в профиль в тёмной студии",
    ),
    _unsplash(
        "stock_hood",
        "about-hood-headlight.jpg",
        "MN3_noM5mCo",
        "Eyosias G",
        "yozz_t",
        "Капот и фара чёрного автомобиля с цветными бликами света",
    ),
    _unsplash(
        "stock_polish_detail",
        "polishing-headlight-detail.jpg",
        "dlJelFmdpOc",
        "Deniz Demirci",
        "ddography",
        "Мастер обрабатывает кузов у фары",
    ),
    _unsplash(
        "stock_wheel",
        "wheel-yellow-caliper.jpg",
        "Lcf_zmcnhpk",
        "Anton Jansson",
        "antonjphotos",
        "Колёсный диск с жёлтым тормозным суппортом",
    ),
    _unsplash(
        "stock_dashboard",
        "interior-dashboard-cleaning.jpg",
        "5SmPnmCjwcU",
        "Luay Barani",
        "luaybarani",
        "Детейлер чистит торпедо автомобиля кистью",
    ),
    _render(
        "render_hero", "render-hero-front34.jpg", "Визуализация: чёрный спорткар в тёмной студии, длинные блики на лаке"
    ),
    _render("render_hero_mobile", "render-hero-mobile.jpg", "Визуализация: чёрный спорткар спереди три четверти"),
    _render("render_profile", "render-profile.jpg", "Визуализация: автомобиль в профиль в тёмной студии"),
    _render("render_front", "render-front-headlights.jpg", "Визуализация: автомобиль анфас с включёнными фарами"),
    _render("render_rear", "render-rear34.jpg", "Визуализация: автомобиль сзади три четверти"),
    _render("render_fender_after", "render-fender-after.jpg", "После: глубокий блеск крыла (визуализация)"),
    _render("render_fender_before", "render-fender-before.jpg", "До: тусклое окисленное крыло (визуализация)"),
    _render("render_door_after", "render-door-after.jpg", "После: ровные блики на двери без голограмм (визуализация)"),
    _render("render_door_before", "render-door-before.jpg", "До: голограммы и царапины на двери (визуализация)"),
    _render("render_interior_after", "render-interior-after.jpg", "После: чистый салон (визуализация)"),
    _render("render_interior_before", "render-interior-before.jpg", "До: пыль и пятна в салоне (визуализация)"),
    _render("render_bumper_film", "render-bumper-film.jpg", "Под плёнкой: бампер без сколов (визуализация)"),
    _render("render_bumper_chips", "render-bumper-chips.jpg", "Без защиты: сколы на бампере (визуализация)"),
    _render("render_droplets", "render-ceramic-droplets.jpg", "Визуализация: капли воды на керамическом покрытии"),
    _render("render_wheel", "render-wheel-caliper.jpg", "Визуализация: колёсный диск и суппорт крупным планом"),
]

# Where the seed puts images (by media key). Everything is replaceable in the panel.
GROUP_IMAGES = {
    "polishing": "stock_polishing",
    "ceramic": "stock_ceramic",
    "ppf": "stock_film_dark",
    "interior": "stock_interior",
    "complex": "stock_profile",
}
GROUP_GALLERIES = {
    "polishing": [
        ("stock_polishing", ""),
        ("stock_hood", ""),
        ("render_fender_after", "ПОСЛЕ"),
        ("render_fender_before", "ДО"),
    ],
    "ceramic": [("stock_ceramic", ""), ("stock_droplets", "")],
    "ppf": [("stock_film_dark", ""), ("stock_film_blue", ""), ("render_bumper_film", "ПОД ПЛЁНКОЙ")],
    "interior": [("stock_interior", ""), ("stock_dashboard", "")],
    "complex": [("stock_profile", ""), ("stock_hero", "")],
}
SECTION_IMAGES = {
    ("hero", "image_id"): "stock_hero",
    ("hero", "mobile_image_id"): "stock_hero_mobile",
    ("about", "image_id"): "stock_hood",
    ("final_cta", "image_id"): "stock_final",
}
MATERIAL_TILE_IMAGES = ["stock_droplets", "stock_film_blue", "stock_polish_detail", "stock_wheel"]

PORTFOLIO = [
    {
        "title": "Восстановление блеска",
        "short_title": "Блеск кузова",
        "description": "Окисленный, «уставший» лак и глубокий чёрный с чёткими бликами после полировки и керамики.",
        "works": "Восстановительная полировка, керамика в 2 слоя",
        "term": "3 дня",
        "before": "render_fender_before",
        "after": "render_fender_after",
    },
    {
        "title": "Удаление дефектов ЛКП",
        "short_title": "Дефекты ЛКП",
        "description": (
            "Голограммы и паутинка от автоматических моек убраны без перекраса, только абразивной полировкой."
        ),
        "works": "Трёхэтапная полировка, защитный силант",
        "term": "2 дня",
        "before": "render_door_before",
        "after": "render_door_after",
    },
    {
        "title": "Химчистка салона",
        "short_title": "Химчистка",
        "description": (
            "Пыль, пятна на коже и следы на ковриках, а после работы чистая кожа с естественной матовой фактурой."
        ),
        "works": "Химчистка салона, уход за кожей",
        "term": "1 день",
        "before": "render_interior_before",
        "after": "render_interior_after",
    },
    {
        "title": "Защитная оклейка",
        "short_title": "Плёнка",
        "description": "Слева бампер без защиты после сезона, справа такой же бампер под плёнкой.",
        "works": "Полиуретановая плёнка, зоны риска",
        "term": "3 дня",
        "before": "render_bumper_chips",
        "after": "render_bumper_film",
        "before_label": "БЕЗ ЗАЩИТЫ",
        "after_label": "ПОД ПЛЁНКОЙ",
    },
]

REVIEWS = [
    {
        "text": "Сдал машину на полировку и керамику. На приёмке под лампой показали каждую царапину и честно "
        "сказали, что уйдёт, а что нет. Так и получилось.",
        "service_label": "ПОЛИРОВКА + КЕРАМИКА",
        "rating": 5,
    },
    {
        "text": "Делали химчистку после зимы: светлая кожа снова светлая, запаха химии нет. Отдельно понравились "
        "фото по ходу работы, не нужно было звонить и спрашивать.",
        "service_label": "ХИМЧИСТКА",
        "rating": 5,
    },
    {
        "text": "Оклеили зоны риска, кромки почти не видно. Пришлось подождать на день дольше, чем планировали, "
        "но предупредили заранее и объяснили почему.",
        "service_label": "ЗАЩИТНАЯ ПЛЁНКА",
        "rating": 4,
    },
]

GIFTS = [
    ("10 000 ₽", "10 000 ₽", "На любые услуги студии"),
    ("25 000 ₽", "25 000 ₽", "На любые услуги студии"),
    ("50 000 ₽", "50 000 ₽", "На любые услуги студии"),
    ("100 000 ₽", "100 000 ₽", "На любые услуги студии"),
    ("Услуга на выбор", "Комплексный уход", "Мойка, полировка, керамика и химчистка"),
]

GROUP_TAGLINES = {
    "polishing": "Блеск без голограмм и паутинки",
    "ceramic": "Защита и гидрофобный эффект",
    "ppf": "Зоны риска или весь кузов",
    "interior": "Кожа, алькантара, ткань, запахи",
    "complex": "Мойка, полировка, керамика кузова и химчистка салона за одно посещение.",
}
