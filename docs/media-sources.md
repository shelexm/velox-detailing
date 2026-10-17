# Источники изображений

Все стартовые изображения лежат в `app/seed/media/` и при первом запуске (`python -m app.cli seed`)
импортируются в медиатеку студии. После этого любое фото заменяется, удаляется, загружается или
переставляется в админке; файлы из репозитория больше не используются.

Данные этой таблицы взяты из `app/seed/media_data.py` (там же alt-тексты), хеши и размеры посчитаны по файлам.
Те же автор, источник и лицензия сохраняются в медиатеке у каждого изображения и выводятся на странице `/credits`.

## Фотографии Unsplash

Лицензия [Unsplash License](https://unsplash.com/license): бесплатное коммерческое и некоммерческое
использование, указание автора не обязательно (мы его всё равно указываем). Нельзя продавать фото
без изменений и собирать из них конкурирующий фотосток. Это стоковые снимки, а не работы VÉLOX:
на сайте они иллюстрируют услуги и не выдаются за портфолио.

| Ключ | Файл | Размер | Автор | Источник | Лицензия | SHA-256 (начало) | Где используется после seed |
|---|---|---|---|---|---|---|---|
| `stock_hero` | `stock/hero-sportscar-dark.jpg` | 2400×1371, 100 КБ | [Tuna Ekici](https://unsplash.com/@tunaekici) | [ссылка](https://unsplash.com/photos/0xySZZ8OK1o) | [Unsplash License](https://unsplash.com/license) | `910322614f24c5dd` | галерея `complex`; секция `hero` (image_id) |
| `stock_hero_mobile` | `stock/hero-mobile-car-front.jpg` | 2400×3602, 349 КБ | [Ville Kaisla](https://unsplash.com/@villekaisla) | [ссылка](https://unsplash.com/photos/HNCSCpWrVJA) | [Unsplash License](https://unsplash.com/license) | `077191237767b65f` | секция `hero` (mobile_image_id) |
| `stock_final` | `stock/final-car-headlights.jpg` | 2400×1600, 96 КБ | [Graham Pengelly](https://unsplash.com/@grahampengelly_) | [ссылка](https://unsplash.com/photos/ifC-l1kPLCs) | [Unsplash License](https://unsplash.com/license) | `fee37c622be20847` | секция `final_cta` (image_id) |
| `stock_polishing` | `stock/polishing-orbital-hood.jpg` | 2400×1047, 552 КБ | [Luay Barani](https://unsplash.com/@luaybarani) | [ссылка](https://unsplash.com/photos/iXpjQNP__EQ) | [Unsplash License](https://unsplash.com/license) | `4fea893a8eea57c0` | карточка услуги `polishing`; галерея `polishing` |
| `stock_ceramic` | `stock/ceramic-raindrops-car.jpg` | 2400×1600, 710 КБ | [Tuomas Nylund](https://unsplash.com/@tuomasnylund) | [ссылка](https://unsplash.com/photos/fi9zsbf3f5Y) | [Unsplash License](https://unsplash.com/license) | `674801fccf3eb889` | карточка услуги `ceramic`; галерея `ceramic` |
| `stock_droplets` | `stock/ceramic-water-droplets.jpg` | 2400×1492, 816 КБ | [Christian Lue](https://unsplash.com/@christianlue) | [ссылка](https://unsplash.com/photos/GqSVfquxyoo) | [Unsplash License](https://unsplash.com/license) | `58c54e1fd96d9395` | галерея `ceramic`; плитка материалов 1 |
| `stock_film_dark` | `stock/film-panel-peel-dark.jpg` | 2400×1600, 281 КБ | [Clarity Coat](https://unsplash.com/@claritycoat) | [ссылка](https://unsplash.com/photos/rsaYn6mq2qo) | [Unsplash License](https://unsplash.com/license) | `fdde091b5937646a` | карточка услуги `ppf`; галерея `ppf` |
| `stock_film_blue` | `stock/film-panel-peel-blue.jpg` | 2400×1600, 278 КБ | [Clarity Coat](https://unsplash.com/@claritycoat) | [ссылка](https://unsplash.com/photos/G6sI_6B_FFY) | [Unsplash License](https://unsplash.com/license) | `aa571a2166076fd4` | галерея `ppf`; плитка материалов 2 |
| `stock_interior` | `stock/interior-cognac-leather.jpg` | 2400×1351, 542 КБ | [Pheng Moua](https://unsplash.com/@phengmua) | [ссылка](https://unsplash.com/photos/T9CSi3hKV7Q) | [Unsplash License](https://unsplash.com/license) | `c9ae8ea0a8b9d2cc` | карточка услуги `interior`; галерея `interior` |
| `stock_profile` | `stock/complex-sedan-profile.jpg` | 2400×1500, 207 КБ | [Samuele Errico Piccarini](https://unsplash.com/@samuele_piccarini) | [ссылка](https://unsplash.com/photos/FMbWFDiVRPs) | [Unsplash License](https://unsplash.com/license) | `ad9b61adbdb7f547` | карточка услуги `complex`; галерея `complex` |
| `stock_hood` | `stock/about-hood-headlight.jpg` | 2400×1600, 529 КБ | [Eyosias G](https://unsplash.com/@yozz_t) | [ссылка](https://unsplash.com/photos/MN3_noM5mCo) | [Unsplash License](https://unsplash.com/license) | `c480768915cd4658` | галерея `polishing`; секция `about` (image_id) |
| `stock_polish_detail` | `stock/polishing-headlight-detail.jpg` | 2400×1600, 818 КБ | [Deniz Demirci](https://unsplash.com/@ddography) | [ссылка](https://unsplash.com/photos/dlJelFmdpOc) | [Unsplash License](https://unsplash.com/license) | `1443887b8de96ae3` | плитка материалов 3 |
| `stock_wheel` | `stock/wheel-yellow-caliper.jpg` | 2400×3599, 735 КБ | [Anton Jansson](https://unsplash.com/@antonjphotos) | [ссылка](https://unsplash.com/photos/Lcf_zmcnhpk) | [Unsplash License](https://unsplash.com/license) | `a25c097e9564ba8e` | плитка материалов 4 |
| `stock_dashboard` | `stock/interior-dashboard-cleaning.jpg` | 2400×1349, 315 КБ | [Luay Barani](https://unsplash.com/@luaybarani) | [ссылка](https://unsplash.com/photos/5SmPnmCjwcU) | [Unsplash License](https://unsplash.com/license) | `db59d45be004aa4f` | галерея `interior` |

## Визуализации из макета

3D-рендеры, которые были в макетах Claude Design (`design-reference/`). Модель «Car Concept»:
Eric Chadwick / Darmstadt Graphics Group, репозиторий Khronos glTF Sample Assets, лицензия
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (нужно указывать автора: сделано на `/credits`).
В блоке «До и после» эти пары подписаны «Примеры работ»: это визуализации, а не реальные работы студии.
Их стоит заменить на фото настоящих работ через админку (раздел «Портфолио»).

| Ключ | Файл | Размер | Автор | Источник | Лицензия | SHA-256 (начало) | Где используется после seed |
|---|---|---|---|---|---|---|---|
| `render_hero` | `design/render-hero-front34.jpg` | 2880×1620, 176 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `648accdc1ab35d9e` | только в медиатеке |
| `render_hero_mobile` | `design/render-hero-mobile.jpg` | 1170×1800, 80 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `4847c3d7a295c91f` | только в медиатеке |
| `render_profile` | `design/render-profile.jpg` | 2400×1000, 126 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `e99d8589ac0f7db4` | только в медиатеке |
| `render_front` | `design/render-front-headlights.jpg` | 2880×1400, 152 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `77d337aad2bcc4b2` | только в медиатеке |
| `render_rear` | `design/render-rear34.jpg` | 1600×1000, 75 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `74413f7371d43b0e` | только в медиатеке |
| `render_fender_after` | `design/render-fender-after.jpg` | 1600×1000, 155 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `91d65035d8b300db` | галерея `polishing`; до/после «Блеск кузова», после |
| `render_fender_before` | `design/render-fender-before.jpg` | 1600×1000, 159 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `010f06fd16b877bc` | галерея `polishing`; до/после «Блеск кузова», до |
| `render_door_after` | `design/render-door-after.jpg` | 1600×1000, 98 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `f6e1b4627bd120b4` | до/после «Дефекты ЛКП», после |
| `render_door_before` | `design/render-door-before.jpg` | 1600×1000, 299 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `6cc43e3ee92bbdfc` | до/после «Дефекты ЛКП», до |
| `render_interior_after` | `design/render-interior-after.jpg` | 1600×1000, 195 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `1bdd550b76c1963e` | до/после «Химчистка», после |
| `render_interior_before` | `design/render-interior-before.jpg` | 1600×1000, 212 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `3dfafbd38475e688` | до/после «Химчистка», до |
| `render_bumper_film` | `design/render-bumper-film.jpg` | 1600×1000, 80 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `47bcce6509b6c1ca` | галерея `ppf`; до/после «Плёнка», после |
| `render_bumper_chips` | `design/render-bumper-chips.jpg` | 1600×1000, 105 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `0d6ad0395729fb72` | до/после «Плёнка», до |
| `render_droplets` | `design/render-ceramic-droplets.jpg` | 1600×1200, 136 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `69e4ad36127f640e` | только в медиатеке |
| `render_wheel` | `design/render-wheel-caliper.jpg` | 1200×1200, 147 КБ | Eric Chadwick / Darmstadt Graphics Group (модель Car Concept), визуализация из макета | [ссылка](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `f9e9fefdd33db765` | только в медиатеке |

## Шрифты и текстура

| Ресурс | Где | Лицензия |
|---|---|---|
| Unbounded, Onest, JetBrains Mono (woff2 из макета) | `static/fonts/` | SIL Open Font License 1.1, текст в `static/fonts/OFL.txt` |
| Текстура зерна `grain.png` | `static/img/` | из макета (сгенерированный шум) |

## Как заменить

Экраны медиатеки появляются в админке на этапе 6; правила обработки уже работают в `app/services/media.py`.

1. Админка, раздел «Медиатека»: загрузить файл (JPG, PNG, WebP или AVIF; до 5 МБ). Сервер сам удаляет EXIF и GPS
   и готовит AVIF, WebP и JPEG шириной 480, 960, 1600 и 2400 px.
2. Указать alt и, если фото чужое, автора, источник и лицензию.
3. Выбрать фото в нужном месте: карточка услуги, галерея, секция лендинга, плитка материалов или пара «До и после».
4. Ненужное фото удалить. Удаление запрещено, пока фото где-то используется: админка покажет где.
