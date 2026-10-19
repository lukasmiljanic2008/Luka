"""Evaluacija classla/wav2vec2-xls-r-juznevesti-sr na EuroSpeech (serbia).

Proširenje prvobitne skripte:
  * nasumičan uzorak (ne samo prvih N segmenata jedne sednice)
  * segmenti sa ciframa u referenci se izbacuju (čišćenje bi ih obrisalo,
    a model broj izgovara rečima -> lažne greške)
  * isti rečnik skraćenica/varijanti pisanja na obe strane
  * WER/CER po segmentu + greške na granicama segmenta, sve u CSV/JSON
"""
import argparse
import csv
import json
import re

import jiwer
import torch
from datasets import load_dataset
from transformers import pipeline

CIR_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'ђ': 'đ', 'е': 'e',
    'ж': 'ž', 'з': 'z', 'и': 'i', 'ј': 'j', 'к': 'k', 'л': 'l', 'љ': 'lj',
    'м': 'm', 'н': 'n', 'њ': 'nj', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's',
    'т': 't', 'ћ': 'ć', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'č',
    'џ': 'dž', 'ш': 'š'
}

# Varijante koje nisu greška modela; primenjuju se na referencu i predikciju
VARIJANTE = {
    r"\bni jedan\b": "nijedan",
    r"\bod kada\b": "otkada",
    r"\buredu\b": "u redu",
    r"\bza to\b": "zato",
}

# Zapisnik razrešava skraćenice, govornik ih izgovara skraćeno
SKRACENICE = {
    r"\bdemokratske stranke srbije\b": "dss",
    r"\bsocijalističke partije srbije\b": "sps",
    r"\bsrpsk\w* naprednoj stranci\b": "sns",
    r"\bdemokratsk\w* strank\w*\b": "ds",
    r"\bsnsu?\b": "sns",
    r"\bdsa\b": "ds",
}


def ocisti_tekst(tekst):
    if not tekst:
        return ""
    tekst = tekst.lower()
    for c, l in CIR_TO_LAT.items():
        tekst = tekst.replace(c, l)
    # Zadržava samo naša latinična slova i razmake
    tekst = re.sub(r"[^abcčćdđefghijklmnoprsštuvzž ]", " ", tekst)
    tekst = re.sub(r"\s+", " ", tekst).strip()
    for obrazac, zamena in {**VARIJANTE, **SKRACENICE}.items():
        tekst = re.sub(obrazac, zamena, tekst)
    return tekst


def greske_na_granici(ref, hyp, sirina=3):
    """Broj grešaka koje padaju u prvih/poslednjih `sirina` reči reference."""
    n = len(ref.split())
    rez = jiwer.process_words(ref, hyp)
    ukupno = 0
    for c in rez.alignments[0]:
        if c.type == "equal":
            continue
        if c.ref_start_idx < sirina or c.ref_end_idx > n - sirina:
            ukupno += max(c.ref_end_idx - c.ref_start_idx,
                          c.hyp_end_idx - c.hyp_start_idx)
    return ukupno


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="classla/wav2vec2-xls-r-juznevesti-sr")
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-sekundi", type=float, default=2.0)
    p.add_argument("--izlaz", default="rezultati")
    args = p.parse_args()

    device = 0 if torch.cuda.is_available() else -1
    print("Učitavam model...")
    pipe = pipeline("automatic-speech-recognition", model=args.model,
                    device=device, chunk_length_s=30, stride_length_s=5)

    dataset = load_dataset("disco-eth/EuroSpeech", "serbia", split="train",
                           streaming=True)
    dataset = dataset.shuffle(seed=args.seed, buffer_size=1000)

    redovi, reference, predikcije = [], [], []
    preskoceno = {"cifre": 0, "kratko": 0}
    for primer in dataset:
        if len(reference) >= args.n:
            break
        raw_reference = primer["human_transcript"]
        audio = primer["audio"]
        trajanje = len(audio["array"]) / audio["sampling_rate"]
        if re.search(r"\d", raw_reference):
            preskoceno["cifre"] += 1
            continue
        if trajanje < args.min_sekundi:
            preskoceno["kratko"] += 1
            continue

        izlaz = pipe({"raw": audio["array"], "sampling_rate": audio["sampling_rate"]})
        ref = ocisti_tekst(raw_reference)
        hyp = ocisti_tekst(izlaz["text"])
        if not ref:
            continue
        reference.append(ref)
        predikcije.append(hyp)

        w = jiwer.process_words(ref, hyp)
        redovi.append({
            "id": len(reference),
            "trajanje_s": round(trajanje, 2),
            "reci": len(ref.split()),
            "wer": round(w.wer, 4),
            "cer": round(jiwer.cer(ref, hyp), 4),
            "S": w.substitutions, "D": w.deletions, "I": w.insertions,
            "greske_na_granici": greske_na_granici(ref, hyp),
            "referenca": ref,
            "model": hyp,
        })
        print(f"[{len(reference)}/{args.n}] WER {w.wer:.0%}")

    rw = jiwer.process_words(reference, predikcije)
    rc = jiwer.process_characters(reference, predikcije)
    ukupno_gresaka = rw.substitutions + rw.deletions + rw.insertions
    na_granici = sum(r["greske_na_granici"] for r in redovi)
    sazetak = {
        "model": args.model,
        "segmenata": len(reference),
        "preskoceno": preskoceno,
        "wer": round(rw.wer, 4),
        "cer": round(rc.cer, 4),
        "reci_u_referenci": rw.hits + rw.substitutions + rw.deletions,
        "C": rw.hits, "S": rw.substitutions,
        "D": rw.deletions, "I": rw.insertions,
        "udeo_gresaka_na_granici": round(na_granici / max(ukupno_gresaka, 1), 4),
    }

    with open(f"{args.izlaz}_segmenti.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(redovi[0].keys()))
        writer.writeheader()
        writer.writerows(redovi)
    with open(f"{args.izlaz}_sazetak.json", "w", encoding="utf-8") as f:
        json.dump(sazetak, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 40)
    print(json.dumps(sazetak, ensure_ascii=False, indent=2))
    print("=" * 40)


if __name__ == "__main__":
    main()
