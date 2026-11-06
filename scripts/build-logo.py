#!/usr/bin/env python3
"""Rebuild the established HERMIN mark as outlined SVG and transparent HD PNG.
Development-only dependency: pycairo. No fonts or Cairo dependency at runtime.
"""
from pathlib import Path
import cairo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'hermin/assets'
WIDTH, HEIGHT = 504, 168


def draw(context):
    context.set_source_rgb(198/255,207/255,175/255)
    context.rectangle(14,14,144,144);context.fill()
    context.set_source_rgb(23/255,23/255,23/255)
    context.rectangle(8,8,144,144);context.fill()
    context.set_source_rgb(1,1,1)
    context.move_to(53,48);context.line_to(68,48);context.line_to(68,74)
    context.line_to(93,74);context.line_to(93,48);context.line_to(108,48)
    context.line_to(108,112);context.line_to(93,112);context.line_to(93,87)
    context.line_to(68,87);context.line_to(68,112);context.line_to(53,112)
    context.close_path();context.fill()
    context.set_source_rgb(23/255,23/255,23/255)
    context.select_font_face('Liberation Sans',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD)
    context.set_font_size(72);context.move_to(196,80)
    context.text_path('HERMIN');context.fill()
    title_width=context.text_extents('HERMIN').width
    context.select_font_face('Noto Sans Mono',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_NORMAL)
    context.set_font_size(20)
    label='HERMES ADMIN'
    widths=[context.text_extents(char).x_advance for char in label]
    spacing=(title_width-sum(widths))/(len(label)-1)
    x=196;context.set_source_rgb(94/255,96/255,93/255)
    for char,advance in zip(label,widths):
        context.move_to(x,128);context.text_path(char);context.fill();x+=advance+spacing


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with cairo.SVGSurface(str(OUTPUT/'hermin-logo.svg'),WIDTH,HEIGHT) as surface:
        draw(cairo.Context(surface))
    svg=OUTPUT/'hermin-logo.svg'
    content=svg.read_text();position=content.index('>',content.index('<svg'))+1
    svg.write_text(content[:position]+'\n<title>HERMIN · Hermes Admin</title>\n'+content[position:])
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,3024,1008)
    context=cairo.Context(surface);context.scale(6,6);draw(context)
    surface.write_to_png(str(OUTPUT/'hermin-logo.png'))
    print('SVG paths + transparent PNG 3024×1008:',OUTPUT)


if __name__=='__main__':main()
