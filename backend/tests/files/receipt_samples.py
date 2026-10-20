"""Sample OCR outputs used by the receipt parser tests."""

UA_ATB = """\
ТОВ «АТБ-МАРКЕТ»
Магазин №1234
м. Київ, вул. Хрещатик, 1
ПН 123456789012
Хліб білий               24,50 А
Молоко 2.5% 0.9л         38,90 А
2.000 X 19,99
Банан ваг.               39,98 А
СУМА                    103,38
ПДВ А 20%                17,23
КАРТКА                  103,38
ЧЕК № 0001234
12.03.2026 18:42:07
ФН 4000123456
"""

UA_FUEL = """\
WOG
ТОВ "ВОГ РІТЕЙЛ"
АЗС №45 м. Львів
А-95 Mustang     42.15 л
Ціна              56.99
ДО СПЛАТИ:      2 402,13 грн
СУМА ЗНИЖКИ        50,00
ГОТІВКА          2 500,00
РЕШТА               97,87
05.10.2026
"""

EN_SUPERMARKET = """\
FRESH MART SUPERMARKET
123 Main Street
Tel: 555-0100
Milk 1L                  $2.49
Bread                    $3.10
Eggs 12pk                $4.99
SUBTOTAL                $10.58
TAX                      $0.85
TOTAL                   $11.43
CASH                    $20.00
CHANGE                   $8.57
10/04/2026 09:15
Thank you for shopping!
"""

EN_THOUSANDS = """\
Comfy
Laptop ASUS Vivobook   1,234.50
Mouse                     25.00
Grand Total            1,259.50 USD
2026-09-30
"""

CAFE_SPLIT_TOTAL = """\
Кав'ярня Aroma Kava
Капучино          65,00
Круасан           55,00
Разом
120,00
11.10.2026 08:05
"""

GARBLED = """\
~~ ### ..
l1l1 ;;; ''
"""

# Real Tesseract output (ukr, --psm 6) for fixtures/receipt_mcdonalds_ua.jpg after
# crop + binarisation + noise-line filtering. Note the OCR slips ("КакДдональдз").
UA_MCDONALDS_OCR = """\
ПІІ "КакДдональдз Юкрейн Лтгд"
Закусочна
М. Львів, прос. Червоної калини 6056
Гаряча лінія: 0-800-50-15-79
ПН О 237444526652
Макарчук Б Каса 26
---- НОМЕР ЗВМОВЛЕННЯ: (- -- -
і КЯАПУЧИНО ВЕЛИКЕ 83.00 8
ж 2 ЦУКОр
: ТЕРМІНЯЛ :51312878
- БЕЗГОТІВКОВА 83.00 грн
: Картка
Сума 83.00
ПДВ.Я Я - 20.005 13.83
ЧЕК к 000143953 00007
3.10.2026 10:37:35
"""

UA_MCDONALDS_QR = [
    "https://cabinet.tax.gov.ua/cashregs/check?date=20261003&time=1037&id=143953&sm=83.00&fn=3001021466",
    "https://feedback.mcdonalds.com/jfe/form/SV_8cgJgr3eaqCulam?CountryRegion=UKRAINE",
]

# What the old pipeline (whole photo, no crop) produced for the same receipt.
UA_MCDONALDS_OLD_PIPELINE = """\
М';М“ М ee A ее UY eS pe ee eee =|
= i —— нн н
——— н Se Макарчук Б Kaca 26 ш SS я --
' ЇЇ% Зн еен н = ——————————
Se a ee ee ———= some = = SSS т ан
AT OUARBAHK ee
то ee = ——- mip.a а- 20.008 5 вЕ я
"""

# Real Tesseract passes for fixtures/receipt_mcdonalds_ua_2.jpg (same receipt, crumpled,
# fiscal QR not decodable): (text, quality) per pass, best first. No pass alone has
# everything — "Сума" lost its decimals, the date reads "3.19.2026", "грн" reads "гри".
UA_MCDONALDS_PHOTO2_PASSES = [
    ("""\
ШІ МЗКЦЦ
Гаряча ””Пя Зргонп% К?Є"93 6Об
Тн 237444526652 |
я
БЕЗГОТІВКОВЯ 83.00 гри
Картка
розкахи про візит,
-
-Ф------,--и----цпимццто--м-.щ-а----.-....
вон н
кяйіййно ВЕЛИКЕ 83.00 д
укор
ЕТІЗ 49248373?ЖЖХХХХ2
ПДВ.Я Я : 20. 00% 13.Е
ЧЕК і 000і43953 00907
3.19.2026 10:37:
ФфІісКкальний ЧЬК 0
""", 0.68),
    ("""\
3 рвин
«АпУЧИНО ВЕЛИКЕ 83.00 й
ж 2 ЦУКОР Ш
КОД ТРАНЗ. 627656666354
Картка
розкажи про візит,
Сума 83. 0
Щ ПДВ.А 8 - 20.005 15
ЧЕК ж о90443953 00007
""", 0.69),
    ("""\
ANATIRHA CHCTENA: VISA
KO’ TPAH3. 627656666354
KOA ABT. 931054
BEST OT IBKOBA 83.00 FPH
_ WBA A= 20.003 13.
UEK & 000143953 00007
""", 0.64),
]

# The English pass on photo 1 read the total as 63.00; the VAT line still says 13.83.
EN_PASS_MISREAD_TOTAL = """\
KANYYHHO BENKKE 83.00 A
Cyma 63.00
NABLA A = 20.00% 13.83
3.10.2026 10:37:35
"""

# What the no-OpenCV fallback (whole photo, Pillow only) read from fixtures/receipt_mcdonalds_ua.jpg:
# the "Сума" and date lines are lost, "грн" reads "ГРя", the shop name is unreadable.
UA_MCDONALDS_PILLOW_FALLBACK = """\
Ї Закусочна
о Пьвів, прос. Червоної калини 605
Гаряча лінія: 0-800-50-15-79
Макарчук Б Каса 26
КАПУЧИНО ВЕЛИКЕ
ж 2 ЦУкор
БЕЗГОТІВКОВА 83.00 ГРя
розкахи про візит»
"""
