"""Landing page blocks: one Pydantic model per block validates what the panel saves into site_sections.content.

The defaults are the texts of the design mockups (long dashes replaced, designer notes and placeholders removed).
They are only the starting point; every text, list and image here is editable in the panel.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text import with_https

Short = Annotated[str, Field(max_length=120)]
Line = Annotated[str, Field(max_length=300)]
Paragraph = Annotated[str, Field(max_length=800)]
ImageRef = Annotated[int | None, Field(default=None, ge=1)]


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LabelText(Block):
    label: Short
    text: Line


class TitleText(Block):
    title: Short
    text: Line = ""


class IconItem(Block):
    icon: Annotated[str, Field(pattern="^(master|gauge|drop|plan|check|shield)$")] = "check"
    title: Short
    text: Line


class Tile(Block):
    eyebrow: Short
    title: Short
    text: Line = ""
    image_id: ImageRef = None


class NameValue(Block):
    name: Short
    value: Short = ""


class Step(Block):
    title: Short
    text: Line
    duration: Short = ""


class Hero(Block):
    eyebrow: Short = "СТУДИЯ ДЕТЕЙЛИНГА"
    title_lines: list[Short] = Field(default=["Совершенство", "в каждой детали"], min_length=1, max_length=3)
    lead: Paragraph = (
        "Профессиональный уход за автомобилем: полировка, керамика и защитные плёнки на премиальных составах. "
        "Каждый этап проверяем под инспекционным светом."
    )
    lead_mobile: Paragraph = (
        "Полировка, керамика и защитные плёнки на премиальных составах, с проверкой под инспекционным светом."
    )
    cta_primary: Short = "ЗАПИСАТЬСЯ ОНЛАЙН"
    cta_secondary: Short = "ПОСМОТРЕТЬ РАБОТЫ"
    cta_telegram: Short = "или запишитесь через Telegram"
    image_id: ImageRef = None
    mobile_image_id: ImageRef = None
    quality: list[LabelText] = Field(
        default=[
            LabelText(label="ИНСПЕКЦИОННЫЙ СВЕТ", text="4000–6500 K, видно каждый дефект"),
            LabelText(label="ТОЛЩИНОМЕР ЛКП", text="Замер до и после каждой работы"),
            LabelText(label="СОСТАВЫ", text="Сертифицированная керамика и плёнки"),
            LabelText(label="ГАРАНТИЯ", text="На керамику и плёнку по паспорту"),
        ],
        max_length=6,
    )


class Services(Block):
    eyebrow: Short = "01 - УСЛУГИ И ПАКЕТЫ"
    title: Short = "Уход, который видно под любым светом"
    lead: Paragraph = (
        "Пять направлений: от одной полировки до полного цикла. Перед работой мастер осматривает автомобиль "
        "вместе с вами и предлагает только то, что действительно нужно покрытию."
    )
    lead_mobile: Paragraph = "Перед работой мастер осматривает автомобиль вместе с вами и предлагает только нужное."
    prices_link: Short = "Все цены и сроки"
    more_label: Short = "Подробнее"
    book_label: Short = "ЗАПИСАТЬСЯ"
    note: Line = "* Итоговая стоимость зависит от размера автомобиля и состояния покрытия."


class Works(Block):
    eyebrow: Short = "02 - РАБОТЫ"
    title: Short = "До и после без фильтров"
    title_mobile: Short = "До и после"
    lead: Paragraph = "Перетащите линию, чтобы сравнить состояние до и после работ."
    lead_mobile: Paragraph = "Двигайте линию пальцем, чтобы сравнить."
    example_label: Short = "ПРИМЕРЫ РАБОТ"
    drag_hint: Short = "← ПЕРЕТАЩИТЕ ЛИНИЮ →"


class Prices(Block):
    eyebrow: Short = "03 - ПРАЙС-ЛИСТ"
    title: Short = "Цены и сроки"
    lead: Paragraph = (
        "Цены для седана среднего размера. Для кроссоверов и больших автомобилей назовём точную сумму после "
        "осмотра, до начала работ."
    )
    lead_mobile: Paragraph = "Для седана среднего размера."
    column_label: Short = "СРОК · ЦЕНА"
    packages_title: Short = "ПАКЕТЫ"
    choose_label: Short = "ВЫБРАТЬ"
    packages_note: Line = "Итоговую стоимость фиксируем в заказ-наряде после осмотра, до начала работ."


class Telegram(Block):
    eyebrow: Short = "VÉLOX В TELEGRAM"
    title: Short = "Запись в два касания прямо в мессенджере"
    lead: Paragraph = (
        "Бот подберёт услугу, покажет свободные даты и напомнит о визите. Перенести или отменить запись "
        "можно там же, без звонка в студию."
    )
    features: list[TitleText] = Field(
        default=[
            TitleText(title="Подбор услуги", text="Ориентир по цене и сроку сразу в чате"),
            TitleText(title="Свободное время", text="Даты и время выбираются прямо в Telegram"),
            TitleText(title="Напоминания", text="За день и за пару часов до визита"),
            TitleText(title="Перенос и отмена", text="В пару касаний, без звонка"),
        ],
        max_length=6,
    )
    cta: Short = "ОТКРЫТЬ БОТА"
    qr_hint: Short = "Наведите камеру, откроется бот"


class About(Block):
    eyebrow: Short = "04 - СТУДИЯ"
    title: Short = "Почему нам доверяют ключи"
    lead: Paragraph = (
        "Небольшая студия, где каждый автомобиль ведёт один мастер. Мы не берём больше машин, чем можем "
        "сделать без спешки."
    )
    image_id: ImageRef = None
    image_caption: Short = "ПРОВЕРКА ПОД СВЕТОМ 6500 K"
    items: list[IconItem] = Field(
        default=[
            IconItem(
                icon="master", title="Опыт мастеров", text="Новые специалисты проходят стажировку на стандартах студии."
            ),
            IconItem(
                icon="gauge",
                title="Профессиональное оборудование",
                text="Эксцентриковые и роторные машинки, толщиномер, инспекционные лампы, ИК-сушка для керамики.",
            ),
            IconItem(
                icon="drop",
                title="Премиальные материалы",
                text="Сертифицированные составы и плёнки. Паспорт материала отдаём вместе с автомобилем.",
            ),
            IconItem(
                icon="plan",
                title="Индивидуальный подход",
                text="План работ составляем после осмотра: учитываем толщину лака, возраст автомобиля "
                "и то, как вы на нём ездите.",
            ),
            IconItem(
                icon="check",
                title="Контроль качества",
                text="Перед выдачей проверяем под тремя типами света и делаем фотоотчёт. "
                "Принимаете работу вместе с мастером.",
            ),
            IconItem(
                icon="shield",
                title="Честные гарантии",
                text="На керамику и плёнку по паспорту производителя. На полировку и химчистку гарантии нет: "
                "это разовый результат, его фиксирует фотоотчёт.",
            ),
        ],
        max_length=9,
    )


class Materials(Block):
    eyebrow: Short = "05 - МАТЕРИАЛЫ И ТЕХНОЛОГИИ"
    title: Short = "Химия, плёнка и свет"
    lead: Paragraph = (
        "Работаем с ограниченным набором проверенных материалов, поэтому результат предсказуем. "
        "Названия составов и плёнок указываем в заказ-наряде."
    )
    tiles: list[Tile] = Field(
        default=[
            Tile(
                eyebrow="КЕРАМИКА",
                title="Кварцевое покрытие в 2 слоя",
                text="Отверждение под ИК-лампами, гидрофобный эффект с первого дня.",
            ),
            Tile(eyebrow="ПЛЁНКА", title="Полиуретан около 200 мкм", text="Глянец или мат, самовосстановление."),
            Tile(
                eyebrow="ПОЛИРОВКА",
                title="Многоэтапные системы",
                text="Пасты и пэды подбираем по толщине и твёрдости лака",
            ),
            Tile(
                eyebrow="ДИСКИ",
                title="Керамика дисков и суппортов",
                text="Со снятием колёс, включая внутреннюю сторону",
            ),
        ],
        max_length=4,
    )
    equipment_title: Short = "ОБОРУДОВАНИЕ"
    equipment: list[NameValue] = Field(
        default=[
            NameValue(name="Толщиномер ЛКП", value="до / после"),
            NameValue(name="Инспекционный свет", value="4000–6500 K"),
            NameValue(name="ИК-сушка керамики", value="отверждение"),
            NameValue(name="Эксцентрики", value="15 / 21 мм"),
            NameValue(name="Пароочиститель салона", value="без химии"),
        ],
        max_length=8,
    )


class Process(Block):
    eyebrow: Short = "06 - КАК МЫ РАБОТАЕМ"
    title: Short = "Пять шагов от записи до выдачи"
    steps: list[Step] = Field(
        default=[
            Step(
                title="Выбор услуги и запись",
                text="Онлайн, по телефону или в мессенджере. Перезвоним, подтвердим время и ответим на вопросы.",
                duration="5 МИН",
            ),
            Step(
                title="Осмотр автомобиля",
                text="Вместе смотрим кузов под светом, замеряем толщину ЛКП, фиксируем состояние на фото.",
                duration="30 МИН",
            ),
            Step(
                title="Подготовка и работы",
                text="Мойка и очистка, затем работы по согласованному плану. Фото этапов присылаем в мессенджер.",
                duration="ПО УСЛУГЕ",
            ),
            Step(
                title="Проверка качества",
                text="Мастер и второй специалист проверяют каждый элемент под тремя типами света.",
                duration="1 Ч",
            ),
            Step(
                title="Выдача автомобиля",
                text="Показываем результат, передаём паспорт материалов и памятку по уходу.",
                duration="20 МИН",
            ),
        ],
        max_length=8,
    )


class Reviews(Block):
    eyebrow: Short = "07 - ОТЗЫВЫ"
    title: Short = "Что говорят клиенты"
    demo_label: Short = "ДЕМО"
    source_label: Short = "Оригинал отзыва"
    all_reviews_label: Short = "Все отзывы на картах"
    all_reviews_url: Annotated[str | None, Field(default=None, max_length=500, pattern=r"^https://")] = None

    _link = field_validator("all_reviews_url", mode="before")(with_https)


class Gift(Block):
    eyebrow: Short = "08 - ПОДАРОЧНЫЕ СЕРТИФИКАТЫ"
    title: Short = "Подарите безупречный автомобиль"
    lead: Paragraph = (
        "На сумму или на конкретную услугу. Электронный сертификат пришлём после оплаты, в конверте можно "
        "забрать в студии."
    )
    cta: Short = "ВЫБРАТЬ СЕРТИФИКАТ"
    card_title: Short = "ПОДАРОЧНЫЙ СЕРТИФИКАТ"
    validity: Short = "ДЕЙСТВУЕТ 12 МЕСЯЦЕВ"
    number_sample: Short = "№ VX-0000-0000"


class Contacts(Block):
    eyebrow: Short = "09 - КОНТАКТЫ И ЗАПИСЬ"
    title: Short = "Запишитесь на услугу или осмотр"
    title_mobile: Short = "Запишитесь онлайн"
    map_image_id: ImageRef = None
    tab_online: Short = "Записаться онлайн"
    tab_telegram: Short = "Записаться через Telegram"
    submit_label: Short = "ЗАПИСАТЬСЯ"
    consent_text: Line = "Я согласен на обработку персональных данных в соответствии с политикой обработки данных"
    success_title: Short = "Заявка принята"
    success_text: Line = "мы перезвоним в течение рабочего часа, чтобы подтвердить время."


class FinalCta(Block):
    title: Short = "Ваш автомобиль заслуживает большего"
    lead: Paragraph = "Запишитесь на осмотр: мастер оценит состояние покрытия и предложит программу ухода."
    cta: Short = "ЗАПИСАТЬСЯ НА ДЕТЕЙЛИНГ"
    image_id: ImageRef = None


class Footer(Block):
    about: Line = "Студия детейлинга: полировка, керамика, защитные плёнки и химчистка салона."


class Seo(Block):
    title: Annotated[str, Field(max_length=70)] = "VÉLOX Detailing Studio: полировка, керамика, защитные плёнки"
    description: Annotated[str, Field(max_length=200)] = (
        "Студия детейлинга VÉLOX: полировка кузова, керамическое покрытие, защитная плёнка и химчистка салона. "
        "Онлайн-запись."
    )


# Order of the landing page blocks by default; footer and seo are not reorderable.
SECTION_MODELS: dict[str, type[Block]] = {
    "hero": Hero,
    "services": Services,
    "works": Works,
    "prices": Prices,
    "telegram": Telegram,
    "about": About,
    "materials": Materials,
    "process": Process,
    "reviews": Reviews,
    "gift": Gift,
    "contacts": Contacts,
    "final_cta": FinalCta,
    "footer": Footer,
    "seo": Seo,
}
FIXED_SECTIONS = ("hero", "footer", "seo")

SECTION_TITLES = {
    "hero": "Первый экран",
    "services": "Услуги",
    "works": "До и после",
    "prices": "Цены и пакеты",
    "telegram": "Telegram",
    "about": "Студия",
    "materials": "Материалы",
    "process": "Как мы работаем",
    "reviews": "Отзывы",
    "gift": "Сертификаты",
    "contacts": "Контакты и запись",
    "final_cta": "Финальный призыв",
    "footer": "Подвал",
    "seo": "SEO",
}


def validate_section(key: str, content: dict) -> dict:
    model = SECTION_MODELS[key]
    return model.model_validate(content).model_dump(mode="json")


def default_content(key: str) -> dict:
    return SECTION_MODELS[key]().model_dump(mode="json")
