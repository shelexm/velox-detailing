"""Starting data taken from the design mockups (prices, durations, masters, hours).

Everything here is only the initial state: the studio edits it in the admin panel, and the seed never
overwrites rows that already exist. Contacts are left empty on purpose (the mockups only had placeholders).
"""

from __future__ import annotations

from datetime import time

STUDIO = {"slug": "velox", "name": "VÉLOX Detailing Studio", "timezone": "Europe/Moscow"}

# Pn-Sb 09:00-21:00, Vs 10:00-18:00 ("Контакты" block); weekday 0 = Monday.
STUDIO_HOURS = {wd: (time(9), time(21)) for wd in range(6)} | {6: (time(10), time(18))}
STUDIO_BREAKS = {wd: [(time(13), time(13, 30))] for wd in range(5)}

RESOURCES = ["Бокс 1", "Бокс 2"]

# key -> data; hours per weekday, None = day off ("Расписание" screen).
STAFF = {
    "andrey": {
        "full_name": "Андрей Ковалёв",
        "short_name": "Андрей К.",
        "title": "Старший мастер",
        "specializations": ["Полировка", "Керамика", "Диски"],
        "client_selectable": True,
        "hours": [(9, 18), (9, 18), (9, 18), (9, 18), (9, 18), (10, 16), None],
    },
    "maxim": {
        "full_name": "Максим Романов",
        "short_name": "Максим Р.",
        "title": "Мастер",
        "specializations": ["Полировка", "Мойка"],
        "client_selectable": True,
        "hours": [None, (10, 19), (10, 19), (10, 19), (10, 19), (10, 21), (10, 18)],
    },
    "ilya": {
        "full_name": "Илья Соколов",
        "short_name": "Илья С.",
        "title": "Мастер",
        "specializations": ["Защитная плёнка"],
        "client_selectable": True,
        "hours": [(9, 18), (9, 18), (9, 18), (9, 18), (9, 18), None, None],
    },
    "elena": {
        "full_name": "Елена Орлова",
        "short_name": "Елена О.",
        "title": "Мастер",
        "specializations": ["Химчистка", "Уход за кожей"],
        # "Онлайн-запись: через студию"
        "client_selectable": False,
        "hours": [(10, 19), None, (10, 19), None, (10, 19), (10, 19), (10, 18)],
    },
}

CATEGORIES = [
    ("body", "Кузов"),
    ("protection", "Защита"),
    ("interior", "Салон"),
    ("extra", "Дополнительно"),
    ("packages", "Пакеты"),
]

# Landing page cards ("01 - УСЛУГИ И ПАКЕТЫ") and their detail pages.
# Chip labels in the mobile booking form (3.html).
GROUP_SHORT_TITLES = {
    "polishing": "Полировка",
    "ceramic": "Керамика",
    "ppf": "Плёнка",
    "interior": "Химчистка",
    "complex": "Комплекс",
}

GROUPS = [
    {
        "slug": "polishing",
        "title": "Полировка кузова",
        "summary": "Возвращаем глубину цвета и зеркальный блеск: убираем голограммы, паутинку и мелкие царапины.",
        "features": [
            "Замер толщины ЛКП на каждом элементе",
            "2–3 этапа под ваш тип лака",
            "Финальная проверка под светом 6500 K",
        ],
        "price_label": "от 25 000 ₽*",
        "duration_label": "1–2 дня",
        "detail": {
            "description": (
                "Возвращаем глубину цвета и зеркальный блеск. Убираем голограммы, паутинку и мелкие царапины, "
                "снимая минимально возможный слой лака."
            ),
            "includes": [
                "Мойка и очистка глиной",
                "Замер толщины ЛКП",
                "Абразивная полировка",
                "Финиш и обезжиривание",
                "Проверка под светом 4000 / 6500 K",
                "Защитный силант на 1–2 месяца",
            ],
            "term": "1–2 дня",
            "cost": "от 25 000 ₽*",
            "guarantee": "Не предусмотрена: фотоотчёт до и после",
            "upsell": "Чтобы блеск держался годами, закрепите результат керамикой: со скидкой на подготовку.",
            "footnote": "* Точная цена после осмотра.",
        },
    },
    {
        "slug": "ceramic",
        "title": "Керамическое покрытие",
        "summary": "Твёрдый прозрачный слой поверх лака: блеск держится дольше, реагенты и грязь хуже, мойка быстрее.",
        "features": [
            "Подготовительная полировка включена",
            "Гидрофобный эффект: вода скатывается",
            "Гарантия по паспорту состава",
        ],
        "price_label": "от 45 000 ₽*",
        "duration_label": "2–3 дня",
        "detail": {},
    },
    {
        "slug": "ppf",
        "title": "Защитная плёнка",
        "summary": (
            "Прозрачный полиуретан на зоны риска или весь кузов: сколы, песок и мелкие царапины остаются на плёнке."
        ),
        "features": [
            "Мелкие царапины затягиваются от тепла",
            "Кромки заворачиваем за край детали",
            "Глянцевая или матовая плёнка",
        ],
        "price_label": "от 90 000 ₽*",
        "duration_label": "2–7 дней",
        "detail": {},
    },
    {
        "slug": "interior",
        "title": "Химчистка салона",
        "summary": (
            "Деликатно чистим кожу, алькантару, ткань, потолок и ковры. Убираем пятна и запахи, кожу кондиционируем."
        ),
        "features": [
            "pH-нейтральные составы для кожи",
            "Сушка без разводов и запаха химии",
            "Озонирование по запросу",
        ],
        "price_label": "от 15 000 ₽*",
        "duration_label": "6–8 часов",
        "detail": {},
    },
    {
        "slug": "complex",
        "title": "Комплексный уход",
        "summary": (
            "Полный цикл за одно посещение: детейлинг-мойка, восстановительная полировка, керамика кузова и "
            "химчистка салона. Один мастер ведёт автомобиль от приёмки до выдачи."
        ),
        "features": [
            "Фотоотчёт после каждого этапа",
            "Дешевле, чем по отдельности",
            "Приёмка работы вместе с мастером",
            "Гарантия на керамику по паспорту",
        ],
        "price_label": "от 70 000 ₽*",
        "duration_label": "3 дня",
        "badge": "РЕКОМЕНДУЕМ",
        "is_wide": True,
        "detail": {},
    },
]

# Price list ("03 - ПРАЙС-ЛИСТ") and packages. Durations: the upper bound of the shown range is booked.
SERVICES = [
    {
        "slug": "detailing-wash",
        "category": "body",
        "group": None,
        "name": "Детейлинг-мойка",
        "short": "Двухфазная ручная мойка, диски и проёмы",
        "price": 4500,
        "minutes": 180,
        "label": "2–3 ч",
        "staff": ["maxim"],
        "selection": "studio",
    },
    {
        "slug": "light-polish",
        "category": "body",
        "group": "polishing",
        "name": "Лёгкая полировка",
        "short": "Один этап: глубина цвета и блеск",
        "price": 14000,
        "minutes": 480,
        "label": "6–8 ч",
        "staff": ["andrey", "maxim"],
    },
    {
        "slug": "restorative-polish",
        "category": "body",
        "group": "polishing",
        "name": "Восстановительная полировка",
        "short": "2–3 этапа: голограммы, паутинка, царапины",
        "price": 25000,
        "days": 2,
        "label": "1–2 дня",
        "staff": ["andrey", "maxim"],
    },
    {
        "slug": "ceramic-coating",
        "category": "protection",
        "group": "ceramic",
        "name": "Керамическое покрытие",
        "short": "2 слоя, подготовка ЛКП включена",
        "price": 45000,
        "days": 3,
        "label": "2–3 дня",
        "staff": ["andrey"],
    },
    {
        "slug": "ppf-risk-zones",
        "category": "protection",
        "group": "ppf",
        "name": "Плёнка: зоны риска",
        "short": "Капот, крылья, бампер, фары, зеркала",
        "price": 90000,
        "days": 3,
        "label": "2–3 дня",
        "staff": ["ilya"],
    },
    {
        "slug": "ppf-full",
        "category": "protection",
        "group": "ppf",
        "name": "Плёнка: полная оклейка",
        "short": "Весь кузов, кромки за край детали",
        "price": 280000,
        "days": 7,
        "label": "5–7 дней",
        "staff": ["ilya"],
        "online": False,
        "note": "Только после осмотра",
    },
    {
        "slug": "interior-cleaning",
        "category": "interior",
        "group": "interior",
        "name": "Химчистка салона",
        "short": "Сиденья, потолок, ковры, пластик",
        "price": 15000,
        "minutes": 480,
        "label": "6–8 ч",
        "staff": ["elena"],
        "selection": "studio",
    },
    {
        "slug": "leather-care",
        "category": "interior",
        "group": "interior",
        "name": "Уход за кожей",
        "short": "Очистка и кондиционирование",
        "price": 6000,
        "minutes": 180,
        "label": "2–3 ч",
        "staff": ["elena"],
        "selection": "studio",
    },
    {
        "slug": "ozonation",
        "category": "interior",
        "group": "interior",
        "name": "Озонирование",
        "short": "Удаление стойких запахов",
        "price": 3000,
        "minutes": 60,
        "label": "1 ч",
        "staff": ["elena"],
        "selection": "studio",
    },
    {
        "slug": "wheel-ceramic",
        "category": "extra",
        "group": None,
        "name": "Керамика дисков",
        "short": "Со снятием колёс, с внутренней стороны",
        "price": 12000,
        "minutes": 300,
        "label": "4–5 ч",
        "staff": ["andrey", "maxim"],
    },
    {
        "slug": "rain-repellent",
        "category": "extra",
        "group": None,
        "name": "Антидождь",
        "short": "Гидрофоб на все стёкла",
        "price": 3500,
        "minutes": 60,
        "label": "1 ч",
        "staff": ["maxim"],
        "selection": "studio",
    },
    {
        "slug": "headlight-film",
        "category": "extra",
        "group": "ppf",
        "name": "Плёнка на фары",
        "short": "Полиуретан, защита от сколов",
        "price": 9000,
        "minutes": 120,
        "label": "2 ч",
        "staff": ["ilya"],
    },
    {
        "slug": "package-fresh",
        "category": "packages",
        "group": None,
        "kind": "package",
        "name": "Свежесть",
        "short": "Мойка, химчистка и лёгкая полировка",
        "price": 32000,
        "days": 2,
        "label": "1–2 дня",
        "items": ["Детейлинг-мойка", "Химчистка салона", "Лёгкая полировка"],
        "staff": ["andrey", "maxim"],
        "selection": "studio",
    },
    {
        "slug": "package-shine",
        "category": "packages",
        "group": "complex",
        "kind": "package",
        "name": "Блеск и защита",
        "short": "Мойка, полировка, керамика и химчистка",
        "price": 70000,
        "days": 3,
        "label": "3 дня",
        "badge": "РЕКОМЕНДУЕМ",
        "note": "Оптимально для автомобиля старше года: 3 дня.",
        "items": ["Детейлинг-мойка", "Восстановительная полировка", "Керамика в 2 слоя", "Химчистка салона"],
        "staff": ["andrey", "maxim"],
        "selection": "studio",
    },
    {
        "slug": "package-protection",
        "category": "packages",
        "group": None,
        "kind": "package",
        "name": "Под защитой",
        "short": "Плёнка на зоны риска, керамика и диски",
        "price": 125000,
        "days": 5,
        "label": "4–5 дней",
        "items": ["Плёнка на зоны риска", "Керамика остальных элементов", "Керамика дисков"],
        "staff": ["andrey", "ilya"],
        "selection": "studio",
    },
    {
        # "Запишитесь на осмотр": the inspection takes a master but not a box ("Осмотры и выдачи без бокса").
        "slug": "inspection",
        "category": None,
        "group": None,
        "kind": "inspection",
        "name": "Осмотр автомобиля",
        "short": "Мастер оценит состояние покрытия и предложит программу ухода",
        "price": None,
        "minutes": 30,
        "label": "30 мин",
        "staff": ["andrey", "ilya", "maxim"],
        "selection": "studio",
        "requires_resource": False,
        "price_list": False,
    },
]
