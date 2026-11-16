# Suv nazorati — binolar uchun suv monitoringi prototipi

## Muammo va foydalanuvchi

Xonadondagi suv sizishi kech aniqlansa, suv isrofi va boshqa xonadonlarga zarar yetishi mumkin. Security xodimiga tekshirish kerak bo‘lgan xonadonni ajratib ko‘rsatish kerak.

## Yaratilgan yechim

5 ta virtual xonadonning daqiqalik suv sarfini kuzatuvchi mahalliy web-panel. Isolation Forest va davomiylik sharti shubhali oqimni aniqlaydi. Xodim hodisani qabul qiladi, tekshiruv natijasini belgilaydi va tarixni CSV sifatida yuklaydi. Aloqa uzilishi suv hodisasidan alohida ko‘rsatiladi.

## Texnologiyalar

Python, scikit-learn, pandas, NumPy, Streamlit. Isolation Forest normal sun’iy xonadon-kunlarida o‘qitilgan. Validatsiya va test uchun mustaqil kunlar ishlatilgan. Pulli AI API ishlatilmaydi.

## Natija va o‘rganilgan saboq

24 ta sun’iy test kunida AI gibrid usuli 91,1% precision va 88,1% recall berdi (daqiqalar bo‘yicha). 12 sizishli kunning barchasida kamida bir signal chiqdi, lekin 12 oddiy kundan 5 tasida ham ogohlantirish bo‘ldi. AI 20 daqiqalik oddiy qoidadan ustun chiqmadi. Shuning uchun murakkab modelning qiymatini bazaviy qoida bilan tekshirish va yolg‘on signallarni ochiq hisoblash muhimligini ko‘rsatdim.

## Chegaralar

Bu sun’iy ma’lumotli prototip. Haqiqiy hisoblagich ulanmagan va real binoda sifat baholanmagan. SMS, avtomatik suv yopish, doimiy audit bazasi yoki ko‘p foydalanuvchili ruxsatlar mavjud emas. Model sizishni tasdiqlamaydi — xodim tekshiradi.

## Portfolio joylashuvi

Muqova sifatida ishlaydigan panelning haqiqiy skrinshotini qo‘ying. Uning tagida muammo, yechim va cheklovlarni qisqa yozing. 30–60 soniyalik namoyishda sizish → ogohlantirish → qabul qilish → tekshiruvni yakunlashni ko‘rsating. GitHub’da README, kod, sinovlar va metrics.json bo‘lsin; virtual muhitni yuklamang. Mahalliy localhost manzilini ommaviy ishlaydigan demo havolasi deb ko‘rsatmang.
