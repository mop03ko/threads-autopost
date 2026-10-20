"""Render reviewed, text-bound educational diagrams. Never infer art from a post ID."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BG, INK, BLUE, ORANGE, MUTED, LINE = '#F4F1E9', '#152626', '#2759DE', '#EB6D42', '#61716D', '#D9DED5'
FONT_DIR = Path(os.environ.get('EDITORIAL_FONT_DIR', '/usr/share/fonts/truetype/dejavu'))


def font(size, bold=False):
    return ImageFont.truetype(str(FONT_DIR / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')), size)


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def eligible(post, brief, now):
    return (post.get('status') == 'pending'
            and post['scheduled_at'] > now.strftime('%Y-%m-%d %H:%M')
            and post['scheduled_at'] == brief['scheduled_at']
            and text_hash(post['text']) == brief['text_sha256'])


class Card:
    def __init__(self, brief):
        self.im = Image.new('RGB', (W, H), BG)
        self.d = ImageDraw.Draw(self.im)
        self.b = brief
        self.text(72, 64, 'DESIGN NOTES', 23, BLUE, True)
        self.text(1008, 64, '@mop03ko.ai', 23, MUTED, anchor='ra')
        self.d.line((72, 115, 1008, 115), fill=LINE, width=2)
        self.wrap(72, 160, brief['title'], 59, 930, INK, True, max_lines=3)
        self.text(72, 385, brief['eyebrow'], 22, BLUE, True)
        self.d.line((72, 1094, 1008, 1094), fill=LINE, width=2)
        self.wrap(72, 1130, brief['note'], 30, 920, INK, max_lines=3)
        self.text(72, 1282, 'ШИНЭЭР ЗУРСАН СХЕМ · КИНОНЫ КАДР БИШ' if brief['kind'].startswith('film_') else 'ТАЙЛБАРЛАХ ЖИШЭЭ', 18, MUTED)

    def text(self, x, y, value, size=28, color=INK, bold=False, anchor=None):
        self.d.text((x, y), str(value), font=font(size,bold), fill=color, anchor=anchor)

    def wrap(self,x,y,value,size,width,color=INK,bold=False,max_lines=4):
        words=value.split(); lines=[]; line=''
        for word in words:
            candidate=(line+' '+word).strip()
            if self.d.textlength(candidate,font=font(size,bold)) > width and line:
                lines.append(line); line=word
            else: line=candidate
        if line: lines.append(line)
        if len(lines)>max_lines:
            raise ValueError(f'Text overflow in brief {self.b["id"]}: {value}')
        for i,line in enumerate(lines): self.text(x,y+i*int(size*1.35),line,size,color,bold)
        return y+len(lines)*int(size*1.35)

    def box(self,xy,fill='white',outline=None,r=20,width=2):
        self.d.rounded_rectangle(xy,radius=r,fill=fill,outline=outline,width=width)

    def label(self,x,y,value,width=390): self.wrap(x,y,value,25,width,MUTED,max_lines=2)
    def arrow(self,x1,y1,x2,y2,color=BLUE):
        self.d.line((x1,y1,x2,y2),fill=color,width=4)
        self.d.polygon([(x2,y2),(x2-12,y2-8),(x2-12,y2+8)],fill=color)

    def mark(self,cx,cy,size,color=BLUE,detail=False):
        # Original geometric teaching mark; not an existing brand.
        s=size
        self.d.polygon([(cx,cy-s/2),(cx+s/2,cy+s/2),(cx+s/5,cy+s/2),(cx,cy+s/10),
                        (cx-s/5,cy+s/2),(cx-s/2,cy+s/2)],fill=color)
        if detail:
            for k in range(1,4): self.d.line((cx-s*.22,cy+k*s*.08,cx+s*.22,cy+k*s*.08),fill=BG,width=max(1,int(s*.012)))

    def ui(self,x,y,w,h,spaced=True,accent=False):
        self.box((x,y,x+w,y+h),'white',LINE)
        self.box((x+22,y+24,x+w-22,y+60),BLUE if accent else INK,r=7)
        gap=34 if spaced else 12
        for j in range(4):
            yy=y+90+j*(26+gap)
            self.box((x+22,yy,x+w-22,yy+26),BLUE if accent else LINE,r=5)
        self.box((x+22,y+h-65,x+w-22,y+h-25),BLUE,r=9)

    def render(self):
        k=self.b['kind']; labels=self.b['labels']; d=self.d
        if k.startswith('film_'):
            self.film(k)
        elif k=='ratios':
            specs=[(90,600,260,260),(405,568,260,325),(720,657,280,158)]
            for i,(x,y,w,h) in enumerate(specs):
                self.box((x,y,x+w,y+h),'white',BLUE,r=8,width=3)
                radius=min(w,h)*.12
                cx,cy=x+w*.75,y+h*.28
                d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=ORANGE)
                size=min(w,h)*.7
                d.polygon([(x+w*.12,y+h*.85),(x+w*.12+size/2,y+h*.85-size*.6),
                           (x+w*.12+size,y+h*.85)],fill=BLUE)
                self.text(x+w/2,945,labels[i],39,INK,True,anchor='ma')
        elif k in ('logoscale','mascot'):
            for i,(x,s) in enumerate([(240,230),(560,130),(850,64)]):
                self.box((x-135,570,x+135,910),'white')
                if k=='logoscale': self.mark(x,720,s,detail=(i<2))
                else:
                    d.ellipse((x-s/2,720-s/2,x+s/2,720+s/2),fill=BLUE)
                    for xx in (x-s*.18,x+s*.18): d.ellipse((xx-s*.05,720-s*.08,xx+s*.05,720+s*.08),fill='white')
                    d.polygon([(x,720-s*.65),(x+s*.13,720-s*.3),(x-s*.13,720-s*.3)],fill=ORANGE)
                self.label(x-100,955,(['Том','Дунд','Жижиг'][i]),200)
        elif k in ('bleed','trim','safe'):
            self.box((200,460,790,1020),'#F9C8B6',r=0)
            self.box((235,495,755,985),'#CBD7F9',r=0)
            self.box((285,545,705,935),'white',r=0)
            for xy in [(235,495,755,985),(285,545,705,935)]: d.rectangle(xy,outline=BLUE,width=3)
            self.mark(495,710,160)
            self.box((365,835,625,852),LINE,r=3)
            for y,label,color,x in [(470,'BLEED',ORANGE,790),(515,'TRIM',BLUE,755),(900,'SAFE',MUTED,705)]:
                d.line((x,y,840,y),fill=color,width=3); self.text(850,y-13,label,23,color,True)
            for x in [235,755]:
                d.line((x,435,x,478),fill=INK,width=2); d.line((x,1002,x,1045),fill=INK,width=2)
        elif k in ('canvas','crop'):
            for i,x in enumerate([90,590]):
                if k!='canvas' or i==1: self.box((x,560,x+400,960),'white',LINE,r=0)
                if k=='canvas':
                    self.box((x+75,635,x+325,885),'#DDE6FD',BLUE,r=0)
                    if i==1: d.rectangle((x+5,565,x+395,955),outline=ORANGE,width=3)
                    self.mark(x+200,760,125)
                else:
                    d.ellipse((x+240,620,x+330,710),fill=ORANGE)
                    d.polygon([(x+30,900),(x+180,660),(x+365,900)],fill=BLUE)
                    if i==1: d.rectangle((x+150,595,x+355,925),outline=ORANGE,width=7)
                self.label(x,990,labels[i])
            self.arrow(510,760,565,760)
        elif k in ('onboarding','accent','whitespace'):
            self.ui(140,500,325,480,spaced=k!='whitespace',accent=k=='accent')
            if k=='onboarding':
                self.box((615,500,940,980),'white',LINE)
                self.mark(777,665,115)
                self.text(777,785,'Эхлэх',35,INK,True,anchor='ma')
                self.box((655,875,900,935),BLUE)
            else: self.ui(615,500,325,480,True)
            for x,label in zip([140,615],labels): self.label(x,1010,label,340)
        elif k in ('inverse','monochrome'):
            for i,x in enumerate([95,575]):
                dark=(k=='inverse' and i==1)
                self.box((x,530,x+410,960),INK if dark else 'white')
                self.mark(x+205,715,220,'white' if dark else (INK if i else BLUE))
                self.text(x+205,865,'STUDIO',27,'white' if dark else INK,True,anchor='ma')
                self.label(x,995,labels[i])
        elif k=='kerning':
            for y,value in [(555,'A V A'),(790,'AVA')]:
                self.text(540,y,value,136,BLUE,True,anchor='ma')
                d.line((170,y+140,910,y+140),fill=LINE,width=2)
            self.label(100,495,labels[0]); self.label(100,735,labels[1])
        elif k in ('contrast','paragraph'):
            if k=='contrast':
                for i,y in enumerate([550,810]):
                    self.box((100,y,980,y+185),'white')
                    self.text(145,y+58,'Уншихад хялбар уу?',49,'#CACDC8' if i==0 else INK,True)
                    self.label(100,y-45,labels[i])
            else:
                self.text(110,525,'Гарчиг',85,INK,True)
                self.text(110,665,'Дэд гарчиг',47,BLUE,True)
                self.wrap(110,780,'Нэг хэвээр удирдсан бичвэр унших дарааллыг ойлгомжтой болгоно.',34,780,max_lines=3)
                for y in [640,750,950]: d.line((110,y,970,y),fill=LINE,width=2)
        elif k in ('artboards','mockup'):
            specs=([(90,580,250,315),(405,500,230,410),(700,640,300,170)] if k=='artboards'
                   else [(110,500,220,400),(425,580,240,290),(735,600,270,160)])
            for i,(x,y,w,h) in enumerate(specs):
                self.box((x,y,x+w,y+h),'white',INK,r=10,width=3)
                self.mark(x+w/2,y+h/2,min(w,h)*.45)
                if k=='mockup':
                    if i==0: self.box((x+70,y+12,x+150,y+23),INK,r=5)
                    if i==1: d.line((x,y+25,x+w,y+25),fill=LINE,width=3)
                    if i==2:
                        for xx in [x+45,x+w-45]: d.line((xx,y+h,xx,y+h+140),fill=INK,width=9)
                self.label(x,965,labels[i],300)
        elif k in ('system','steps','revision','versions','storyboard','hook','formats'):
            for i,label in enumerate(labels):
                y=480+i*185
                self.box((95,y,985,y+145),'white')
                self.box((120,y+24,215,y+119),BLUE if i!=1 else ORANGE,r=16)
                self.text(167,y+48,str(i+1),36,'white',True,anchor='ma')
                self.wrap(250,y+43,label,36,675,INK,True,max_lines=2)
                if i<2: d.line((168,y+145,168,y+185),fill=LINE,width=4)
        elif k in ('feedback','filenames'):
            for i,y in enumerate([510,795]):
                self.box((95,y,985,y+200),'white')
                self.box((95,y,106,y+200),ORANGE if i==0 else BLUE,r=0)
                self.wrap(140,y+55,labels[i],34,800,INK,i==1,max_lines=3)
                self.text(140,y+160,'ТОДОРХОЙ БОЛГО' if i==0 else 'АШИГЛАЖ БОЛОХ МЭДЭЭЛЭЛ',18,MUTED)
        elif k in ('locking','master'):
            for i,x in enumerate([120,590]):
                self.box((x,490,x+360,990),'white',LINE)
                self.box((x+20,510,x+340,580),BLUE)
                self.text(x+40,530,'Тогтмол хэсэг',25,'white')
                self.box((x+25,620,x+335,870),'#E8EDFA',r=8)
                self.text(x+45,710,'Контент '+str(i+1),30,INK,True)
                self.box((x+20,925,x+340,970),BLUE,r=8)
                self.label(x,1015,labels[i if k=='locking' else i+1],370)
        elif k=='light':
            self.box((100,480,980,1010),'white')
            d.ellipse((200,550,320,670),fill=ORANGE)
            self.arrow(345,655,530,750,ORANGE)
            d.ellipse((555,870,850,930),fill=LINE)
            self.box((535,690,675,895),BLUE,r=24)
            self.box((573,645,637,700),INK,r=9)
            self.label(190,710,'Гэрэл'); self.label(510,550,'Объект'); self.label(720,970,'Сүүдэр')
        elif k=='lighting':
            for i,x in enumerate([150,650]):
                self.box((x-65,520,x+345,960),'white')
                for j in range(3):
                    xx=x+j*100
                    direction=-1 if k=='lighting' and i==0 and j%2 else 1
                    d.ellipse((xx-15+direction*22,845,xx+85+direction*22,875),fill=LINE)
                    self.box((xx,665,xx+65,850),BLUE if j!=1 else ORANGE,r=16)
                    self.box((xx+18,635,xx+47,670),INK,r=6)
                d.ellipse((x-20,560,x+25,605),fill=ORANGE)
                self.arrow(x+40,605,x+130,645,ORANGE)
                self.label(x-60,995,labels[i],400)
        elif k=='filter':
            for i,color in enumerate(['#A8ADA4','#718D7A','#11EE45']):
                x=100+i*320
                self.box((x,540,x+270,900),color)
                d.ellipse((x+150,580,x+220,650),fill='#EDC29C' if i<2 else '#FF5A00')
                d.polygon([(x+20,850),(x+115,650),(x+250,850)],fill='#425C51' if i<2 else '#0911ED')
                self.text(x+135,955,labels[i],37,INK,True,anchor='ma')
            self.text(100,1030,'Схемчилсэн өнгөний жишээ',22,MUTED)
        elif k=='resolution':
            for i,x in enumerate([100,620]):
                self.box((x,550,x+360,950),'white')
                cell=35 if i==0 else 12; start=x+40 if i==0 else x+130
                for row in range(8):
                    for col in range(8):
                        color=BLUE if (row+col)%3 else ORANGE
                        self.box((start+col*cell,610+row*cell,start+(col+1)*cell,610+(row+1)*cell),color,r=0)
                self.label(x,990,labels[i])
        elif k=='print':
            for i,x in enumerate([120,610]):
                self.box((x,540,x+350,950),'white',INK)
                for j,c in enumerate((['#1D52FF','#FF4B60','#F5DA1C'] if i==0 else ['#4665B0','#C36D72','#C4B568'])):
                    self.box((x+35,585+j*100,x+315,665+j*100),c,r=6)
                self.label(x,995,labels[i])
            self.text(105,470,'Схемчилсэн ялгаа · өнгөний proof биш',23,MUTED)
        elif k=='retouch':
            for i,x in enumerate([125,620]):
                self.box((x,560,x+335,940),'#E7BEA6')
                if i:
                    for row in range(14):
                        for col in range(12):
                            xx=x+16+col*26+(row%2)*5; yy=580+row*24
                            d.ellipse((xx,yy,xx+3,yy+3),fill='#B9927B')
                d.arc((x+80,650,x+255,820),0,160,fill='#916753',width=4)
                self.label(x,980,labels[i],380)
            self.text(125,480,'Арьсны бүтцийн схемчилсэн жишээ',23,MUTED)
        elif k=='diagonal':
            self.box((120,470,960,1030),'white')
            d.polygon([(160,920),(220,980),(900,560),(840,500)],fill=BLUE)
            d.ellipse((700,540,880,720),fill=ORANGE)
            self.text(165,500,'ЧИГЛЭЛ',26,INK,True)
            self.text(600,920,'АНХААРЛЫН ЦЭГ',24,INK,True)
        elif k in ('background','focal'):
            for i,x in enumerate([90,580]):
                self.box((x,530,x+410,950),'white')
                if i==0:
                    for j in range(5): self.box((x+15+j*75,550,x+40+j*75,930),ORANGE,r=0)
                self.mark(x+(205 if i==0 else 285),735,190)
                if k=='focal':
                    for j in range(3): self.box((x+35,645+j*50,x+(240 if i==0 else 178),665+j*50),INK,r=2)
                self.label(x,990,labels[i])
        elif k=='icons':
            for i,y in enumerate([580,840]):
                for j,x in enumerate([220,540,860]):
                    width=6 if i else [2,12,5][j]
                    r=20 if i else [0,45,8][j]
                    self.box((x-80,y-65,x+80,y+65),None,BLUE,r=r,width=width)
                    d.line((x-35,y,x+35,y),fill=BLUE,width=width)
                self.label(100,y-125,labels[i])
        else:
            raise ValueError(f'Unknown reviewed diagram kind: {k}')
        return self.im

    def film(self,k):
        d=self.d
        dark='#182425'
        self.box((95,460,985,1040),dark,r=6)
        if k in ('film_collage','film_rough','film_hand'):
            colors=['#C6BBA6','#EBDBBA','#827B6D'] if k=='film_collage' else ['#D8C7A2','#DAA29E','#A57C75']
            for j,(x,y,w,h) in enumerate([(150,530,430,210),(530,600,350,290),(230,795,480,170)]):
                d.polygon([(x,y+15),(x+w-14,y),(x+w,y+h-20),(x+12,y+h)],fill=colors[j])
                for n in range(6):
                    yy=y+35+n*20
                    d.line((x+25,yy,min(x+w-20,x+80+n*26),yy+3),fill=dark,width=2)
            self.text(210,650,'NOTES' if k=='film_collage' else ('FORM' if k=='film_rough' else 'Atelier'),74,dark,True)
            if k=='film_hand':
                for j in range(5): d.arc((350+j*7,650+j*15,870-j*9,940+j*8),10,170,fill='#A53C32',width=4)
            if k=='film_rough':
                for i in range(25):
                    x=140+i*31;d.polygon([(x,510),(x+13,535+i%3*14),(x+25,510)],fill=BG)
        elif k=='film_worlds':
            for i,(x,color) in enumerate([(140,'#26564C'),(565,'#293E65')]):
                self.box((x,510,x+375,990),color,r=4)
                for j in range(5): self.box((x+30+j*65,620-j%2*40,x+75+j*65,920),'#152B2B',r=0)
                self.text(x+40,545,'A' if i==0 else 'B',42,'white',True)
                (d.ellipse if i==0 else d.rectangle)((x+275,545,x+320,590),fill='#A8C5AE' if i==0 else '#9CB8DB')
        elif k=='film_ring':
            d.ellipse((320,530,760,970),outline='#D1AA5B',width=12)
            d.ellipse((350,560,730,940),outline='#927343',width=3)
            for i,ch in enumerate('STORY · FORM · '):
                a=2*math.pi*i/15-math.pi/2
                self.text(540+270*math.cos(a),750+230*math.sin(a),ch,30,'#D1AA5B',True,anchor='mm')
        elif k=='film_bridge':
            self.box((95,460,985,1040),'#284E43',r=6)
            for x,y,s in [(230,560,180),(820,520,240),(160,760,110)]: d.ellipse((x-s/2,y-s/2,x+s/2,y+s/2),fill='#3E6E55')
            d.arc((200,620,880,1060),190,350,fill='#C94D3B',width=38)
            d.line((200,820,880,820),fill='#E16A49',width=30)
            for x in range(240,870,75): d.line((x,725,x,815),fill='#E16A49',width=13)
        elif k=='film_frame':
            for xy,c in [((150,500,930,1010),'#976C42'),((260,550,840,980),'#4E4638'),((365,590,760,955),'#C5945E'),((460,630,690,935),dark)]:
                d.rectangle(xy,fill=c)
            d.ellipse((550,700,605,755),fill='#D17557');self.box((540,755,620,900),'#D17557',r=17)
        elif k=='film_ink':
            d.polygon([(140,980),(140,630),(350,540),(420,700),(610,590),(810,690),(935,550),(935,980)],fill='#F4F1E9')
            d.polygon([(380,980),(470,680),(570,650),(700,980)],fill=dark)
            d.ellipse((477,580,580,690),fill=dark)
            for j in range(5): d.line((170+j*150,500,250+j*150,1000),fill=dark,width=7)
        elif k=='film_organic':
            for i in range(18):
                a=i*.45;x=540+280*math.cos(a);y=750+210*math.sin(a);s=[12,22,35][i%3]
                d.ellipse((x-s,y-s,x+s,y+s),fill=['#5DC8B4','#409EAC','#97DDC6'][i%3])
                d.arc((240+i*8,550+i*5,800,960),180,310,fill='#327D79',width=2)
        elif k=='film_bubble':
            self.box((95,460,985,1040),'#D74993',r=6)
            d.text((540,740),'PLAY',font=font(175,True),anchor='mm',fill='#F28EC2',stroke_width=12,stroke_fill='white')
        elif k=='film_surreal':
            self.box((95,460,985,1040),'#D6DFDB',r=6)
            d.polygon([(320,760),(760,630),(580,880),(525,780),(430,835),(450,775)],fill=dark)
            d.line((450,775,760,630),fill='#809B9E',width=3)
        elif k=='film_condensed':
            f=ImageFont.truetype('/usr/share/fonts/opentype/urw-base35/NimbusSansNarrow-Bold.otf',175)
            for y,word in [(650,'FORM'),(810,'FIRST')]: d.text((540,y),word,font=f,anchor='mm',fill='#EDD6C0')
        elif k=='film_symbol':
            for x,y,s in [(355,750,280),(780,750,85)]:
                d.ellipse((x-s/2,y-s/2,x+s/2,y+s/2),fill='white')
                for xx in [x-s*.15,x+s*.15]: d.ellipse((xx-s*.04,y-s*.03,xx+s*.04,y+s*.03),fill=dark)
        elif k=='film_quiet':
            self.box((95,460,985,1040),'#CAD3D3',r=6)
            d.ellipse((380,515,700,880),fill='#344A4C')
            self.text(540,940,'S I L E N C E',27,dark,anchor='ma')
        else: raise ValueError(k)


def render_briefs(briefs, output):
    output.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for brief in briefs:
        path=output/f"post-{brief['id']:03d}.jpg"
        Card(brief).render().save(path,'JPEG',quality=94,optimize=True,subsampling=0)
        manifest.append({'id':brief['id'],'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'text_sha256':brief['text_sha256'],'kind':brief['kind']})
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--briefs',type=Path,default=Path('image-briefs/2026-10-21.json'))
    parser.add_argument('--output',type=Path,default=Path('editorial-output'))
    args=parser.parse_args()
    briefs=json.loads(args.briefs.read_text())
    render_briefs(briefs,args.output)
    print(f'Rendered {len(briefs)} reviewed illustrations.')


if __name__=='__main__': main()
