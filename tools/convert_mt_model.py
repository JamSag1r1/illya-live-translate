#!/usr/bin/env python3
"""把 HuggingFace 格式的 NLLB/OPUS-MT 转成 CTranslate2 格式（只需在开发机跑一次）。

    python tools/convert_mt_model.py models/nllb-600M-hf models/nllb-200-distilled-600M-ct2

转完之后的目录可以直接喂给 live_translate.py --local-mt <dir>，运行端只需要 ctranslate2
（已经随包），不需要 torch / transformers。

注意：NLLB 的语种标签（jpn_Jpan / zho_Hans）是 tokenizer 的 added token，
用 sentencepiece 单独 encode 会被拆碎——所以推理时要把它们**整块**作为 token 贴在句首，
本脚本末尾会自检这一点。
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import ctranslate2

COPY = ["sentencepiece.bpe.model", "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json"]      # config.json 不拷：CT2 会写自己那份，拷了会冲突


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--quantization", default="int8")
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)

    print(f"[convert] {src.name} → {dst.name} ({a.quantization})")
    t0 = time.time()
    copy = [f for f in COPY if (src / f).is_file()]
    # 注意：ctranslate2 4.8 起 copy_files 是构造参数，不再属于 convert()
    conv = ctranslate2.converters.TransformersConverter(str(src), copy_files=copy)
    conv.convert(str(dst), quantization=a.quantization, force=True)
    print(f"[convert] 完成，用时 {time.time()-t0:.0f}s；{sum(f.stat().st_size for f in dst.rglob('*') if f.is_file())/1e6:.0f} MB")

    # ── 自检：真翻一句 ──
    import sentencepiece as spm
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from live_translate import enable_cuda_dlls
    sp = spm.SentencePieceProcessor(model_file=str(dst / "sentencepiece.bpe.model"))
    if ctranslate2.get_cuda_device_count() > 0:
        enable_cuda_dlls()                     # 不走这一步会报 cublas64_12.dll not found
        tr = ctranslate2.Translator(str(dst), device="cuda", compute_type="int8_float16")
    else:
        tr = ctranslate2.Translator(str(dst), device="cpu", compute_type="int8")
    for text, src_lang in [("ありがとうございます", "jpn_Jpan"),
                           ("今日の配信では化学の話をします", "jpn_Jpan")]:
        toks = [src_lang] + sp.encode(text, out_type=str)
        out = list(tr.translate_batch([toks], target_prefix=[["zho_Hans"]], beam_size=1)[0].hypotheses[0])
        if out and out[0] == "zho_Hans":
            out = out[1:]
        print(f"  {text}  →  {sp.decode(out)}")


if __name__ == "__main__":
    main()
