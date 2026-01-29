#!/usr/bin/env python3
"""
Gemini API를 사용한 YouTube 다국어 메타데이터 번역

사용법:
    # 기본 메타데이터를 모든 YouTube 지원 언어로 번역
    GEMINI_API_KEY=xxx python translate.py --title "제목" --description "설명" -o metadata.json

    # 특정 언어만 번역
    GEMINI_API_KEY=xxx python translate.py --title "제목" --description "설명" --langs ko,en,ja -o metadata.json
"""

import argparse
import json
import os
import sys

import google.generativeai as genai

# YouTube 지원 언어 목록 (ISO 639-1)
YOUTUBE_LANGUAGES = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "az": "Azerbaijani",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fil": "Filipino",
    "fr": "French",
    "gl": "Galician",
    "gu": "Gujarati",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "iw": "Hebrew",
    "ja": "Japanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "ky": "Kyrgyz",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "my": "Burmese",
    "ne": "Nepali",
    "nl": "Dutch",
    "no": "Norwegian",
    "pa": "Punjabi",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sq": "Albanian",
    "sr": "Serbian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "zu": "Zulu",
}


def translate_text(model, text: str, target_lang: str, lang_name: str) -> str:
    """Gemini로 텍스트 번역"""
    prompt = f"""Translate the following text to {lang_name} ({target_lang}).
Only return the translated text, nothing else.
Keep the tone and style appropriate for YouTube video metadata.

Text to translate:
{text}"""

    response = model.generate_content(prompt)
    return response.text.strip()


def translate_metadata(
    model, title: str, description: str, source_lang: str, target_langs: list[str]
) -> dict:
    """메타데이터를 여러 언어로 번역"""
    metadata = {
        "default": {
            "title": title,
            "description": description,
            "language": source_lang,
        }
    }

    total = len(target_langs)
    for i, lang in enumerate(target_langs, 1):
        lang_name = YOUTUBE_LANGUAGES.get(lang, lang)
        print(f"  [{i}/{total}] {lang} ({lang_name})...", end=" ", flush=True)

        try:
            translated_title = translate_text(model, title, lang, lang_name)
            translated_desc = translate_text(model, description, lang, lang_name)

            metadata[lang] = {
                "title": translated_title,
                "description": translated_desc,
            }
            print("완료")
        except Exception as e:
            print(f"실패: {e}")

    return metadata


def main():
    parser = argparse.ArgumentParser(description="YouTube 메타데이터 다국어 번역")

    parser.add_argument("--title", required=True, help="영상 제목")
    parser.add_argument("--description", required=True, help="영상 설명")
    parser.add_argument(
        "--source-lang", default="ko", help="원본 언어 코드 (기본: ko)"
    )
    parser.add_argument(
        "--langs",
        help="번역할 언어 코드 (쉼표 구분). 미지정시 모든 YouTube 지원 언어",
    )
    parser.add_argument("-o", "--output", required=True, help="출력 파일 경로")

    args = parser.parse_args()

    # API 키 확인
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("오류: GEMINI_API_KEY 환경변수가 필요합니다.")
        sys.exit(1)

    # Gemini 설정
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    # 번역할 언어 결정
    if args.langs:
        target_langs = [lang.strip() for lang in args.langs.split(",")]
        # 유효한 언어 코드만 필터링
        invalid = [lang for lang in target_langs if lang not in YOUTUBE_LANGUAGES]
        if invalid:
            print(f"경고: 알 수 없는 언어 코드 무시: {', '.join(invalid)}")
            target_langs = [lang for lang in target_langs if lang in YOUTUBE_LANGUAGES]
    else:
        target_langs = list(YOUTUBE_LANGUAGES.keys())

    # 원본 언어 제외
    target_langs = [lang for lang in target_langs if lang != args.source_lang]

    print(f"번역 시작: {len(target_langs)}개 언어")
    print(f"원본 언어: {args.source_lang}")
    print()

    # 번역 실행
    metadata = translate_metadata(
        model, args.title, args.description, args.source_lang, target_langs
    )

    # 저장
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print()
    print(f"저장 완료: {args.output}")
    print(f"총 {len(metadata) - 1}개 언어 번역됨")


if __name__ == "__main__":
    main()
