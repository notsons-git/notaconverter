<div align="center">

![NotAconverter Hero Banner](docs/images/hero_banner.png)

# NotAconverter

**Десктопная студия для подготовки видеостикеров Telegram.**  
*Любое видео, GIF или фото → готовый WebM (VP9) по спецификации @Stickers.*

[![Version](https://img.shields.io/badge/version-1.2.0-A6FF00?style=for-the-badge&logoColor=0F120E)](https://github.com/notsons-git/notaconverter/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-161A13?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/notsons-git/notaconverter/releases)
[![FFmpeg](https://img.shields.io/badge/engine-FFmpeg%20VP9-273321?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![License](https://img.shields.io/badge/license-MIT-161A13?style=for-the-badge)](LICENSE)

<br/>

<a href="https://github.com/notsons-git/notaconverter/releases/latest">
  <img src="https://img.shields.io/badge/⬇️%20Скачать%20NotAconverter%201.2.0%20(EXE)-A6FF00?style=for-the-badge&labelColor=161A13&color=A6FF00" alt="Download EXE">
</a>
&nbsp;
<a href="https://github.com/notsons-git/notaconverter/releases">
  <img src="https://img.shields.io/badge/📦%20Все%20релизы-161A13?style=for-the-badge&labelColor=0F120E&color=273321" alt="All Releases">
</a>

</div>

---

![Overview](docs/images/header_overview.png)

## О программе

Официальный бот `@Stickers` принимает видеостикеры только при строгом соблюдении нормативов: контейнер **WebM**, кодек **VP9**, **без звука**, вес **до 256 КБ**, длительность **до 3.0 секунд** и одна из сторон ровно **512 px**.

**NotAconverter** решает это в пару кликов:
- Принимает любые видео, анимации и изображения.
- Быстро кадрирует область (включая квадрат `1:1`) и обрезает таймлайн.
- Сохраняет альфа-канал прозрачности для GIF и PNG.
- Автоматически укладывает файл в лимит 256 КБ через адаптивное двухпроходное сжатие VP9.

---

![Interface](docs/images/header_interface.png)

## Интерфейс

<div align="center">

### 1. Главный экран
<p><em>Очередь файлов, быстрое переименование кликом, выбор папки экспорта и статус обработки.</em></p>

![Главный экран](docs/images/screenshot_home.png)

<br/>

### 2. Кадрирование
<p><em>Позиционирование области обрезки, сетка третей и фиксация квадрата 1:1.</em></p>

![Видоискатель кадрирования](docs/images/screenshot_crop.png)

<br/>

### 3. Интерактивный таймлайн
<p><em>Нарезка диапазона, моментальный предпросмотр без задержек и быстрая подгонка под 3 секунды (FIT 3.0s).</em></p>

![Временная шкала](docs/images/screenshot_timeline.png)

<br/>

### 4. Настройки кодирования
<p><em>Регулировка качества CRF, ограничения битрейта, FPS, потоков кодирования и громкости уведомления.</em></p>

![Окно настроек](docs/images/screenshot_settings.png)

<br/>

### 5. Пакетный экспорт
<p><em>Индикация статуса файлов очереди, автонумерация дубликатов и звуковой сигнал по завершении.</em></p>

![Экспорт](docs/images/screenshot_export.png)

</div>

---

![Features](docs/images/header_features.png)

## Возможности

- **Импорт любого медиа:** Видео (`.mp4`, `.mov`, `.mkv`, `.webm`), анимации (`.gif`), графика (`.png`, `.jpg`, `.jpeg`, `.webp`). Drag & Drop файлов и папок.
- **Интерактивное кадрирование:** Пресеты пропорций (`1:1 Square`, `Free Crop`, `4:3`, `16:9`), сетка третей, автоокругление до чётных пикселей.
- **Монтаж на таймлайне:** Точные границы обрезки, кнопка `FIT 3.0s`, управление воспроизведением по клавише Space.
- **Моментальный предпросмотр:** Кадровый кеш в RAM — скраббинг и переключение без задержек и повторных запусков FFmpeg.
- **Сохранение прозрачности:** Полная поддержка альфа-канала (`yuva420p`, VP9 Profile 0/1).
- **Гарантированный вес ≤ 256 КБ:** Кодирование с постоянным качеством CRF и автоматический двухпроходный кламп битрейта при риске переполнения.
- **Удобная очередь:** Инлайн-переименование карточек по клику, автонумерация повторных файлов (`file (1).webm`), индикаторы прогресса.

---

![Telegram Specs](docs/images/header_specs.png)

## Требования Telegram к видеостикерам

| Параметр | Требование Telegram API | В NotAconverter |
| :--- | :--- | :--- |
| **Формат** | `WebM` | `.webm` с потоковыми метаданными |
| **Кодек** | `VP9` (`libvpx-vp9`) | Профиль 0 / Профиль 1 (с прозрачностью `yuva420p`) |
| **Аудио** | Запрещено | Флаг `-an` (полное удаление звука) |
| **Разрешение** | Одна сторона ровно 512 px, вторая $\le 512\text{ px}$ | Автоматическое масштабирование с чётными сторонами |
| **Вес файла** | $\le 256\text{ КБ}$ | Автоматический двухпроходный расчет битрейта |
| **Длительность** | $\le 3.00\text{ с}$ | Нарезка с точностью до сотых секунды, кнопка `FIT 3.0s` |
| **FPS** | До 30 кадров/с | Настраиваемый дециматор частоты кадров |

---

![Installation](docs/images/header_installation.png)

## Установка и запуск

### Готовый файл для Windows (EXE)
1. Откройте [**GitHub Releases**](https://github.com/notsons-git/notaconverter/releases/latest).
2. Скачайте **`NotAconverter-1.2.0.exe`**.
3. Запустите файл (программа автономна, установка не требуется; нужен доступный системный или локальный `ffmpeg`).

### Запуск из исходного кода (Python 3.11+)
```bash
git clone https://github.com/notsons-git/notaconverter.git
cd notaconverter
pip install -r requirements.txt
python main.py
```

### Сборка исполняемого файла
```bash
python build_optimized_exe.py
```
Готовый бинарник будет создан в каталоге `dist/NotAconverter-1.2.0.exe`.

---

![Architecture](docs/images/header_architecture.png)

## Архитектура

```mermaid
flowchart TD
    A["Входной файл (MP4 / GIF / PNG / WebP)"] --> B["Инспекция метаданных (FFprobe / Pillow)"]
    B --> C["Фоновый кадровый кеш (RAM)"]
    C --> D["Видоискатель кадрирования и таймлайн"]
    D --> E["Нормализация геометрии (512px, чётные стороны)"]
    E --> F["Кодирование FFmpeg (VP9, YUVA420P, -an)"]
    F --> G{"Вес <= 256 КБ?"}
    G -- "Да" --> H["Готовый .webm видеостикер"]
    G -- "Нет" --> I["2-Pass адаптивный битрейт-кламп"]
    I --> F
```

---

## Конфиденциальность

- **100% локально:** Все файлы обрабатываются исключительно на вашем ПК. Приложение не использует внешние сервера и не передаёт данные в сеть.
- **Без телеметрии:** Никаких трекеров и скрытой аналитики.
- **Настройки рядом:** Конфигурация хранится в локальном файле `config.json`.

---

## Лицензия

Распространяется под свободной лицензией **[MIT License](LICENSE)**.
