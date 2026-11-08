import sys, os
from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QColor, QFont, QPen, QPolygonF
from PyQt6.QtCore import QPointF, QRectF, Qt

app = QGuiApplication.instance()
if not app:
    app = QGuiApplication(sys.argv)

def draw_logo_chevron(p: QPainter, x: float, y: float, size: float):
    s = size / 512.0
    p.save()
    p.translate(x, y)
    p.scale(s, s)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor('#161A13'))
    p.drawRoundedRect(QRectF(0, 0, 512, 512), 96, 96)
    p.setPen(QPen(QColor('#273321'), 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(2, 2, 508, 508), 94, 94)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor('#FFFFFF'))
    p.drawPolygon(QPolygonF([
        QPointF(112, 144), QPointF(224, 256), QPointF(112, 368),
        QPointF(192, 368), QPointF(304, 256), QPointF(192, 144)
    ]))

    p.setBrush(QColor('#A6FF00'))
    p.drawPolygon(QPolygonF([
        QPointF(240, 144), QPointF(352, 256), QPointF(240, 368),
        QPointF(320, 368), QPointF(432, 256), QPointF(320, 144)
    ]))
    p.restore()

def make_hero_banner():
    w, h = 1200, 300
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor('#0F120E'))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setPen(QPen(QColor('#273321'), 1))
    p.drawRect(0, 0, w - 1, h - 1)

    draw_logo_chevron(p, 60, 55, 190)

    p.setFont(QFont('Segoe UI', 36, QFont.Weight.Black))
    p.setPen(QColor('#FFFFFF'))
    p.drawText(285, 108, 'NotAconverter')

    p.setFont(QFont('Segoe UI', 13, QFont.Weight.DemiBold))
    p.setPen(QColor('#A6FF00'))
    p.drawText(287, 145, 'СТУДИЯ ВИДЕОСТИКЕРОВ TELEGRAM // WEBM VP9')

    p.setFont(QFont('Segoe UI', 11))
    p.setPen(QColor('#929E8A'))
    p.drawText(287, 180, 'Быстрое кадрирование, нарезка и экспорт в WebM со 100% соблюдением спецификации.')

    specs = ['WEBM VP9', 'ALPHA YUVA420P', 'MAX 512×512', 'LIMIT ≤ 256 KB', 'DURATION ≤ 3.0S']
    chip_x = 287
    p.setFont(QFont('Consolas', 9, QFont.Weight.Bold))
    for s in specs:
        tw = len(s) * 8 + 16
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#161A13'))
        p.drawRoundedRect(QRectF(chip_x, 218, tw, 26), 3, 3)
        p.setPen(QPen(QColor('#273321'), 1))
        p.drawRoundedRect(QRectF(chip_x, 218, tw, 26), 3, 3)
        p.setPen(QColor('#A6FF00' if any(k in s for k in ['VP9', 'ALPHA', '256']) else '#E8ECE4'))
        p.drawText(QRectF(chip_x, 218, tw, 26), Qt.AlignmentFlag.AlignCenter, s)
        chip_x += tw + 8

    p.end()
    for dest in ['D:/GITHUB/notaconverter/docs/images', 'D:/GITHUB/notaconverterGEMINI/docs/images']:
        os.makedirs(dest, exist_ok=True)
        img.save(f'{dest}/hero_banner.png')
    print('Saved hero_banner.png')

if __name__ == '__main__':
    make_hero_banner()
