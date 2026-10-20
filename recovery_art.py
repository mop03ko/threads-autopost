"""Eight reviewed, code-native diagrams for the explicitly requested recovery batch."""
from editorial_images import Card, BLUE, INK, ORANGE, BG

BRIEFS = {
817: ('film_biomech','Alien · хоёр өөр бүтэц','CINEMA / CONTRASTING TEXTURES','Нэг бүтэц давамгайлж, нөгөө нь онцлох хэсэг болно.'),
835: ('film_selective','Sin City · ганц өнгө','CINEMA / SELECTIVE COLOR','Нэг өнгөөр нэг л анхаарлын цэгийг тодруул.'),
700: ('steps','AI хувилбар гаргана.\nДизайнер шийднэ.','AI / DESIGN JUDGMENT','Хурд нэмэгдсэн ч эцсийн чанарыг шалгах хариуцлага үлдэнэ.'),
836: ('film_negative','The Dark Knight · таних хэлбэр','CINEMA / NEGATIVE SPACE','Дэвсгэр өөрчлөгдсөн ч танигдах гол хэлбэрээ хадгал.'),
837: ('film_glow','Avatar · гэрэл ба орон зай','CINEMA / LUMINOUS COLOR','Бүх хэсэг гэрэлтвэл онцлох цэг үлдэхгүй.'),
848: ('film_scale','Dune · хэмжээний ялгаа','CINEMA / MONUMENTAL SCALE','Жижиг дүрс том хэлбэрийн хэмжээг ойлгуулдаг.'),
853: ('film_ink','Metropolis · гэрэл ба сүүдэр','CINEMA / VALUE CONTRAST','Саарал өнгөөр, жижиг хэмжээнд ч гол дүрс ялгарч байна уу?'),
856: ('film_complement','Vertigo · өнгөний харьцаа','CINEMA / DOMINANT & ACCENT','Нэг өнгө давамгайлж, нөгөө нь жижиг акцент болно.'),
}


def brief_for(post):
    kind,title,eyebrow,note=BRIEFS[post['id']]
    return {'id':post['id'],'kind':kind,'title':title,'eyebrow':eyebrow,'note':note,
            'labels':['Хувилбар гаргах','Зорилгод нийцүүлж сонгох','Деталь, хэрэглээг шалгах']}


class RecoveryCard(Card):
    def film(self,k):
        d=self.d; dark='#182425'
        if k=='film_ink': return super().film(k)
        self.box((95,460,985,1040),dark,r=6)
        if k=='film_biomech':
            for i in range(12):
                d.arc((200+i*22,505+i*12,850,990-i*6),85,280,fill='#B1B9A1',width=12)
            for x in range(600,900,65):
                self.box((x,585,x+35,930),'#587378',r=3)
                for y in [630,740,850]:d.ellipse((x+10,y,x+25,y+15),fill='#B1B9A1')
        elif k=='film_selective':
            for i,(x,y,w,h) in enumerate([(145,600,130,370),(300,510,170,460),(500,670,130,300),(660,540,145,430),(835,730,95,240)]):
                self.box((x,y,x+w,y+h),'#D8DED8' if i%2 else '#84918B',r=0)
            d.ellipse((524,670,580,726),fill='#F25145')
            self.box((510,724,594,920),'#F25145',r=17)
        elif k=='film_negative':
            for x,y,s,c in [(315,725,240,'#F1EFE3'),(785,725,150,dark)]:
                if x>500:self.box((580,525,945,975),'#F1EFE3',r=4)
                # Original symmetrical wing mark demonstrates silhouette, not a film frame.
                points=[(-.5,-.3),(-.25,-.1),(-.13,-.2),(-.08,-.42),(0,-.3),(.08,-.42),(.13,-.2),(.25,-.1),(.5,-.3),(.35,.15),(.18,.07),(0,.38),(-.18,.07),(-.35,.15)]
                d.polygon([(x+a*s,y+b*s) for a,b in points],fill=c)
        elif k=='film_glow':
            for x,y,r,colors in [(340,725,190,['#233D50','#275A73','#3C87A8','#69CCDB']),
                                  (745,700,110,['#282D49','#423765','#735899','#A888D1'])]:
                for i,c in enumerate(colors):
                    rr=r-i*r*.2; d.ellipse((x-rr,y-rr,x+rr,y+rr),fill=c)
            self.box((200,965,610,985),'#CDDCE0',r=4)
        elif k=='film_scale':
            self.box((95,460,985,1040),'#C9AB7E',r=6)
            d.ellipse((270,490,810,1030),fill='#584D3D')
            d.rectangle((95,935,985,1040),fill='#AD8A5F')
            d.ellipse((605,865,622,882),fill=dark)
            self.box((603,883,625,938),dark,r=5)
            d.line((614,935,608,960),fill=dark,width=5);d.line((616,935,625,960),fill=dark,width=5)
        elif k=='film_complement':
            for x in [135,570]: self.box((x,520,x+375,975),'#315347',r=4)
            d.rectangle((135,520,322,975),fill='#C0473C')
            d.ellipse((795,700,875,780),fill='#D35543')
            self.text(320,995,'Ижил хүчтэй',24,BG,anchor='ma')
            self.text(760,995,'Нэг акцент',24,BG,anchor='ma')
        else: raise ValueError(k)
