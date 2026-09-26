"""Generate privacy-free worksheet fixtures for crop and recognition checks."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def generate(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',62)
    small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',42)
    regions=[(.36,.16,.42,.12,'120'),(.36,.35,.42,.12,'3456'),(.36,.54,.42,.12,'A'),(.36,.73,.42,.12,'<'),]
    for label in ('reference','submission'):
        im=Image.new('RGB',(1000,1400),'white');d=ImageDraw.Draw(im)
        d.rectangle((25,25,975,1375),outline='black',width=3)
        d.text((90,70),'Synthetic math worksheet',font=small,fill='black')
        for index,(x,y,w,h,value) in enumerate(regions,1):
            left=int(x*1000);top=int(y*1400);right=int((x+w)*1000);bottom=int((y+h)*1400)
            d.text((95,top+30),f'Q{index}',font=small,fill='black')
            d.rectangle((left,top,right,bottom),outline='#777777',width=2)
            d.text((left+22,top+35),value,font=font,fill='black')
        im.save(directory/(label+'.png'))
    # Separate crops exercise formula recognition without student photographs.
    for name,top,bottom in (
        ('fraction','1','2'),
        ('vertical','25','17'),
    ):
        im=Image.new('RGB',(420,180),'white');d=ImageDraw.Draw(im)
        d.text((170,12),top,font=font,fill='black')
        d.line((120,90,300,90),fill='black',width=5)
        d.text((170,98),bottom,font=font,fill='black')
        im.save(directory/(name+'.png'))
    im=Image.new('RGB',(600,160),'white')
    ImageDraw.Draw(im).text((32,35),'3 × 4 = 12',font=font,fill='black')
    im.save(directory/'expression.png')
    page=Image.new('RGB',(1000,1400),'white');draw=ImageDraw.Draw(page)
    draw.rectangle((25,25,975,1375),outline='black',width=3)
    draw.text((90,70),'Synthetic formula worksheet',font=small,fill='black')
    draw.text((95,320),'Q1',font=small,fill='black')
    draw.text((465,295),'1',font=font,fill='black')
    draw.line((410,385,600,385),fill='black',width=6)
    draw.text((465,405),'2',font=font,fill='black')
    page.save(directory/'formula_page.png')
    return regions


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args()
    print(generate(args.directory))
