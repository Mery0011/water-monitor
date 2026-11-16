# Suv nazorati

Interfeysning standart tili **English**. Yuqori o‘ngdagi **Language / 언어 / Til** tanlovidan **한국어** yoki **O‘zbekcha**ga o‘tish mumkin. Tugmalar, hodisalar, grafik yorliqlari, hisobot ustunlari va izohlar uch tilda. Tilni almashtirish seansni qayta boshlamaydi; xodim yozgan matn o‘z holicha saqlanadi. Tarjimalar `i18n.py` ichida, model va saqlangan hodisa qiymatlari tildan mustaqil.

Binoda suv sarfidagi noodatiy holatni security xodimiga tekshirtirish uchun mahalliy portfolio prototipi. 5 ta virtual xonadon, Isolation Forest modeli, jonli simulyatsiya va hodisalarni boshqarish oynasi mavjud. Barcha ma’lumotlar sun’iy. Haqiqiy hisoblagich, SMS yoki tashqi bino tarmog‘iga ulanmagan.

## Ishga tushirish

Mac’da `start.command` faylini oching. Brauzer: http://127.0.0.1:8503

Asosiy `ai model` papkasidan terminal orqali:

```sh
.venv/bin/python -m streamlit run water-monitor/app.py --server.port 8503 --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Server terminalini ochiq qoldiring, to‘xtatish uchun Ctrl+C. Agar 8503 band bo‘lsa, mavjud oynadan foydalaning yoki boshqa bo‘sh portni tanlang.

## 2 daqiqalik namoyish

Standart rejim **Jonli vaqt**: grafik Asia/Seoul (UTC+9) mahalliy sana/vaqtiga mos, bir daqiqa bir haqiqiy daqiqadir. Oyna har 2 soniyada yangilanadi, yangi sarf o‘lchovi esa daqiqada bir marta olinadi. Yarim tunda kuzatuv davom etadi. Sarf ma’lumotlari hanuz sun’iy. Jonli rejimda 20 daqiqalik shart real 20 daqiqa kutishni talab qiladi. Quyidagi tez namoyish uchun avval **Tezlashtirilgan demo** rejimini tanlang. Rejimni almashtirish demo seansini qayta boshlaydi.

1. 03-xonadon tanlangan holda “Sizishni boshlash”ni bosing.
2. “+15 daqiqa” tugmasini ikki marta bosing. Virtual vaqt tezlashadi, suv oqimi +0,7 L/min davom etadi. Ushbu demo ssenariysida 20 daqiqadan keyin tekshiruv hodisasi chiqadi.
3. Security panelida “Qabul qilish”ni bosing.
4. “Odatiy holatga qaytarish” va “+15 daqiqa”ni bosing. Signal tugaydi, ammo xodim yakunlamaguncha hodisa ro‘yxatda turadi.
5. “Tekshiruvni yakunlash”dan natija va izohni kiriting, “Yakunlash”ni bosing.
6. Boshqa xonadonda “Aloqani uzish” va “+15 daqiqa” bilan alohida qurilma muammosini ko‘rsating.
7. Dush ssenariysi 15 virtual daqiqada avtomatik tugaydi. Uni sizishdan farqlash misoli sifatida ko‘rsating.
8. “Hodisalar tarixi va hisobot”dan CSV yuklang.

Avtomatik rejimda har 2 soniyada 5 virtual daqiqa o‘tadi; model har bir virtual daqiqani ko‘radi. Qo‘lda qadam ham xuddi shu mantiqdan foydalanadi. Kun 23:59 da to‘xtaydi. Demo chapdagi paneldan qayta boshlanadi. Audio ixtiyoriy, brauzer autoplayni bloklashi mumkin.

## Modelni qanday yaratdik?

- `engine.py`: odatiy qisqa foydalanish, dush, kir yuvish impulslari, ba’zan uzoq normal foydalanish va kichik uzluksiz sizishlarni yaratadi. Bu real xonadon statistikasi emas.
- `train.py`: 60 normal sun’iy xonadon-kunidan 40 000 qatorni olib Isolation Forest’ni o‘qitadi (160 daraxt, max_samples=512, random_state=42).
- Belgilar: hozirgi L/min, oldingi 15/60 daqiqalik o‘rtacha, 15 daqiqalik standart og‘ish, uzluksiz oqim davomiyligi, sutka vaqtining sin/cos qiymatlari. Kelajakdagi qiymatlar ishlatilmaydi.
- 24 boshqa kun validatsiya uchun; ball chegarasi shu yerda F1 bo‘yicha tanlanadi. Chegara normal training ballarining kamida 95-persentiliga teng.
- Gibrid detector: anomaly score chegaradan yuqori **va** oqim kamida 20 daqiqa davom etgan bo‘lishi kerak. Ball sizish ehtimolligi foizi emas.
- Yakuniy test: yana 24 mustaqil kun, 12 sizishli va 12 sizishsiz. To‘plamlar alohida seedlarda yaratiladi. Demo ham boshqa seedlardan foydalanadi.

## Haqiqiy o‘lchangan demo natijalari

Quyidagilar **faqat sun’iy test** uchun. Precision/recall/F1 daqiqa bo‘yicha hisoblangan.

| Usul | Precision | Recall | F1 | Topilgan sizishli kunlar | Signal chiqqan oddiy kunlar | Median kechikish |
|---|---:|---:|---:|---:|---:|---:|
| AI + 20 daqiqa | 91,1% | 88,1% | 89,6% | 12/12 | 5/12 | 19 daq. |
| Oddiy 20 daqiqa qoida | 91,1% | 88,2% | 89,7% | 12/12 | 5/12 | 19 daq. |
| Oddiy 60 daqiqa qoida | 98,5% | 63,3% | 77,0% | 12/12 | 0/12 | 59 daq. |

**Xulosa:** bu sun’iy to‘plamda AI 20 daqiqalik oddiy qoidaga qo‘shimcha foyda ko‘rsatmadi. 60 daqiqa kutish yolg‘on signallarni kamaytirdi, lekin aniqlashni kechiktirdi. Buni “AI har doim yaxshiroq” deb taqdim etmaymiz. Keyingi ilmiy qadam — haqiqiy sarf ma’lumotida baholash va modelga ehtiyoj bor-yo‘qligini tekshirish.

12/12 hodisa topilishi barcha sizish daqiqalari topilgan degani emas: hodisa davomida kamida bir signal yetarli. Kechikish faqat topilgan hodisalar uchun. 20 ta musbat o‘lchov 19 daqiqalik vaqt farqini beradi. 5/12 oddiy kunda signal borligi pilotdan oldin yolg‘on signallar ustida ishlash kerakligini bildiradi.

Panelda birinchi aniqlanishdan keyin hodisa suv oqimi to‘xtaguncha ushlab turiladi: ball tebranishi yangi hodisalar yaratmaydi. Baholash jadvali esa detektorning xom daqiqalik natijasini o‘lchaydi, hodisani ushlab turish siyosatini emas. Bu farq real pilotda alohida o‘lchanishi kerak.

## Security jarayoni

Hodisa: **Yangi → Qabul qilingan → Yakunlangan**. Signal faol/tugagan holati tekshiruv holatidan alohida. Demoda suv hodisasini yakunlash sizish ssenariysini ham to‘xtatadi, joriy sarfni 0 ga tushiradi va xonadonni odatiy holatga qaytaradi. Oldingi grafik va hodisa tarixi saqlanadi. Bu faqat sun’iy ssenariy; haqiqiy klapan boshqarilmaydi. Oqim to‘xtab, keyin yangi hodisa boshlansa yangi ID beriladi. Aloqa uzilishi alohida hodisa; yo‘q o‘lchov uzluksiz oqimni uzadi.

Natijalar va izohlar faqat Streamlit seans xotirasida. Server/seans yopilsa yo‘qolishi mumkin; bu ishlab chiqarish tizimiga mos doimiy audit bazasi emas. CSV — foydalanuvchi yuklab oladigan nusxa. Login, rollar, real xonadon ma’lumoti yoki tarmoq ulanishi bu versiyaga kiritilmagan.

## Qayta o‘qitish va tekshirish

Asosiy papkadan:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r water-monitor/requirements.txt
.venv/bin/python water-monitor/train.py
.venv/bin/python water-monitor/checks.py
```

Sinovlar: kelajak ma’lumoti belgiga aralashmasligi, aloqa uzilishi, 15 daqiqalik dush, sizishdan hodisa ochilishi, takroriy signalni birlashtirish, qabul qilish/yakunlash, yangi sizish uchun yangi hodisa, kun chegarasi va haqiqiy Streamlit tugmalari.

Python 3.14 muhitida tekshirildi. Model bepul scikit-learn kutubxonasi bilan mahalliy ishlaydi; pulli API yoki GPU talab qilmaydi. Joblib faylini faqat ishonchli manbadan yuklang.

## Fayllar

- `app.py`: security paneli.
- `engine.py`: virtual o‘lchovlar, belgilar, detektor va hodisa holatlari.
- `train.py`: o‘qitish, validatsiya, test.
- `artifacts/water_model.joblib`: o‘qitilgan model va threshold.
- `artifacts/metrics.json`: tekshiriladigan baholash natijalari.
- `artifacts/example_day.csv`: alohida sun’iy sinov kuni namunasi.
- `checks.py`: regressiya tekshiruvlari.
- `PORTFOLIO.md`: portfolioga qo‘yiladigan loyiha tavsifi.

## Keyingi bosqich

Haqiqiy qurilma formatini kelishish → bitta sensor bilan pilot → doimiy ma’lumot bazasi → xodimlar login/rollari → tarmoq uzilishida buffer/retry → haqiqiy hodisalar bilan baholash → foydalanish tartibi va ruxsatlar. Shu ishlar bajarilmaguncha binoda ishlatishga tayyor mahsulot deb ko‘rsatilmaydi.
