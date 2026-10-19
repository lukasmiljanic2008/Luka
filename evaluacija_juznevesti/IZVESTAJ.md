# Evaluacija `classla/wav2vec2-xls-r-juznevesti-sr` na EuroSpeech (serbia)

## Rezultat (pilot, 20 segmenata)

| Metrika | Vrednost |
|---|---|
| WER | **32,32%** |
| CER | **15,02%** |
| Reči u referenci | 721 |
| Tačne (C) / Zamene (S) / Brisanja (D) / Umetanja (I) | 508 / 145 / 68 / 20 |

Ovo je tipično ponašanje akustičkog CTC modela bez jezičkog modela (LM) na govoru iz
specifičnog domena. Odnos WER : CER ≈ 2 : 1 pokazuje da model čuje većinu glasova, ali
greške od 1–2 slova po reči u WER-u obaraju celu reč (S = 145).

**Ograničenje:** uzorak je prvih 20 segmenata jedne sednice (`take(20)`); početni segmenti
su procedura predsedavajućeg sa najlošijim granicama. Bez segmenata 1–4 WER je **26,4%**.

## Gde model greši

Svaka od 233 greške razvrstana je automatski (`jiwer` poravnanje + Levenštajnovo rastojanje po reči):

| Tip | Broj |
|---|---|
| Zamena, 1–2 slova razlike | 69 |
| Zamena, veća razlika | 76 |
| Brisanje | 68 |
| Umetanje | 20 |
| **Od toga u prve/poslednje 3 reči segmenta** | **63 (27%)** |

### A. Spajanje reči i nestanak razmaka
U CTC-u je razmak običan karakter. Kad govornik ubrza ili veže proklitiku, verovatnoća
razmaka padne ispod *blank* tokena i reči se spoje. Svako spajanje daje jednu zamenu i jedno brisanje.

- seg. 1: `od ukupnog → odukupno`
- seg. 2: `prelazimo na → prelazemna`
- seg. 10: `u redu → uredu`
- seg. 11: `i nakon → inakon`
- seg. 14: `da odgovorim → daodgovorim`
- seg. 15: `nijedan → ni jedan`, `od kada → otkada` (razdvajanje / spajanje)
- seg. 20: `zato → za to`

### B. Skraćenice stranaka (referenca nije doslovna)
Zapisnik razrešava skraćenice u pun naziv, a model piše ono što je izgovoreno (~14 grešaka):

- seg. 10: `demokratske stranke srbije i socijalističke partije srbije → dstan sa sps`
- seg. 15: `demokratska stranka → ds`
- seg. 18: `demokratske stranke → dsa`
- seg. 19: `srpskoj naprednoj stranci → snsu`

Slično, zapisnik je na nekim mestima uređen: seg. 14 referenca kaže „malo **više** da
komentarišu“, a model je tačno čuo „malo **tiše**“; izbačena su „ja“, „ja bih“ i ponavljanja
(seg. 15 „nismo dobili odgovor nismo dobili…“).

### C. Padežni nastavci i fonetsko nagađanje
Bez dekodera sa jezičkim modelom model ne zna srpsku morfologiju:

- seg. 2: `republike → repike`, `glasova → glasao`
- seg. 3: `razmatranje i odlučivanje → razmatarnije odlučivanju`
- seg. 6: `poslovnik → poslovnek`
- seg. 10: `položaja → položaj`
- seg. 16: `nekom → nekm`
- seg. 19: `kolege → kolegi`

### D. Kratki segmenti (seg. 4)
`hvala → ""` — reč od ~1 s, tiha ili odsečena; ceo izlaz je *blank* → 100% brisanje.

### E. Granice segmenata, šum i preklapanje govornika
27% svih grešaka je u prve/poslednje 3 reči segmenta:

- seg. 1: početak `narodni poslanici pre` nedostaje, na kraju model ima višak `glasanje`
- seg. 13: `hvala konstantin arsenović → rušimohavvećiborsa steflanović` (predsedavajući upada)
- seg. 20: `sali` na početku nedostaje

### F. Brojevi (greška u evaluaciji)
`ocisti_tekst` briše cifre iz reference („članom 112. stav 2.“ → „članom stav“), a model broj
izgovara rečima („stav **dva**“) → lažne greške. Ispravka: izbaciti takve segmente ili cifre
prevesti u reči (uz rizik od padeža).

## Šta bi smanjilo grešku

| # | Promena | Očekivani efekat |
|---|---|---|
| 1 | **Pošteno merenje**: nasumičan uzorak ≥ 300 segmenata, bez segmenata sa ciframa i kraćih od 2 s, ista normalizacija skraćenica/varijanti na obe strane | Samo normalizacija na ovih 20: **32,3% → 29,9%**; sa ostalim ispravkama procena ~24–26% |
| 2 | **Jezički model u dekodiranju**: KenLM 4-gram na skupštinskim tekstovima + `pyctcdecode` | Procena −5 do −8 p.p.; direktno pogađa kategorije A i C |
| 3 | **Dotreniranje na skupštinskom govoru** (EuroSpeech serbia train, bez test sednica) | Najveći potencijal: akustika sale i vokabular („kvorum“, „poslovnik“) |
| 4 | Poređenje sa Whisper large-v3 (`language="serbian"`) | Referentna tačka |
| 5 | `chunk_length_s=30, stride_length_s=5` za duge segmente | Stabilnost na dugim snimcima |

Procene za 2–3 nisu izmerene; treba ih potvrditi na većem uzorku.

## Reprodukcija

```bash
pip install torch transformers datasets jiwer
python eval_juznevesti.py --n 300 --seed 42 --izlaz rezultati
```

Izlaz: `rezultati_segmenti.csv` (WER/CER/S/D/I i greške na granici po segmentu) i
`rezultati_sazetak.json` (ukupni rezultat).
