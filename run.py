#!/usr/bin/env python3
"""
YouTube 다국어 영상 업로드 통합 스크립트

사용법:
    python run.py ./sample/input.json
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv()
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 기본값
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite-preview-06-17"
DEFAULT_SOURCE_LANG = "ko"
DEFAULT_PRIVACY = "private"

# YouTube 지원 언어 목록
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

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = "token.json"


# === Translation ===

DEFAULT_PROMPT_TEMPLATE = """Translate the following text to {lang_name} ({target_lang}).
Only return the translated text, nothing else.
Keep the tone and style appropriate for YouTube video metadata.

Text to translate:
{text}"""


def translate_text(client, text: str, target_lang: str, lang_name: str, model: str, prompt_template: str) -> str:
    """Gemini로 텍스트 번역"""
    prompt = prompt_template.format(
        lang_name=lang_name,
        target_lang=target_lang,
        text=text,
    )

    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response.text.strip()


def translate_single_lang(client, title: str, description: str, lang: str, model: str, prompt_template: str) -> tuple[str, dict | None, str | None]:
    """단일 언어 번역 (병렬 처리용)"""
    lang_name = YOUTUBE_LANGUAGES.get(lang, lang)
    try:
        translated_title = translate_text(client, title, lang, lang_name, model, prompt_template)
        translated_desc = translate_text(client, description, lang, lang_name, model, prompt_template)
        return lang, {"title": translated_title, "description": translated_desc}, None
    except Exception as e:
        return lang, None, str(e)


def translate_metadata(
    client, title: str, description: str, source_lang: str, target_langs: list[str], model: str, prompt_template: str, max_workers: int = 10
) -> dict:
    """메타데이터를 여러 언어로 병렬 번역"""
    metadata = {
        "default": {
            "title": title,
            "description": description,
            "language": source_lang,
        }
    }

    # 원본 언어도 추가
    metadata[source_lang] = {
        "title": title,
        "description": description,
    }

    total = len(target_langs)
    completed = 0
    failed = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(translate_single_lang, client, title, description, lang, model, prompt_template): lang
            for lang in target_langs
        }

        for future in as_completed(futures):
            lang, result, error = future.result()
            completed += 1
            lang_name = YOUTUBE_LANGUAGES.get(lang, lang)

            if result:
                metadata[lang] = result
                print(f"  [{completed}/{total}] {lang} ({lang_name})... 완료")
            else:
                failed.append(lang)
                print(f"  [{completed}/{total}] {lang} ({lang_name})... 실패: {error}")

    if failed:
        print(f"\n실패한 언어: {', '.join(failed)}")

    return metadata


# === YouTube Upload ===

def get_authenticated_service():
    """OAuth 인증 후 YouTube API 서비스 반환"""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print(f"오류: {CLIENT_SECRETS_FILE} 파일이 필요합니다.")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


# YouTube API 언어 코드 변환 (일부 코드가 다름)
YOUTUBE_LANG_MAP = {
    "iw": "he",  # Hebrew
    "zh-CN": "zh-Hans",
    "zh-TW": "zh-Hant",
    "fil": "tl",  # Filipino -> Tagalog
}


def get_supported_languages(youtube) -> set:
    """YouTube API에서 지원하는 언어 코드 목록 조회"""
    try:
        response = youtube.i18nLanguages().list(part="snippet").execute()
        return {item["id"] for item in response.get("items", [])}
    except Exception as e:
        print(f"언어 목록 조회 실패: {e}")
        # 기본 지원 언어 (fallback)
        return {
            "af", "ar", "az", "be", "bg", "bn", "bs", "ca", "cs", "da", "de",
            "el", "en", "es", "et", "fa", "fi", "fr", "gu", "hi", "hr", "hu",
            "hy", "id", "is", "it", "ja", "ka", "kk", "km", "kn", "ko", "ky",
            "lo", "lt", "lv", "mk", "ml", "mn", "mr", "ms", "my", "ne", "nl",
            "no", "pa", "pl", "pt", "ro", "ru", "si", "sk", "sl", "sq", "sr",
            "sv", "sw", "ta", "te", "th", "tl", "tr", "uk", "ur", "uz", "vi",
            "zh-Hans", "zh-Hant", "zu"
        }


def upload_video(youtube, video_path: str, metadata: dict, privacy: str) -> str:
    """영상 업로드 후 video_id 반환"""
    print(f"영상 업로드 중: {video_path}")

    # YouTube 지원 언어 목록 조회
    supported_langs = get_supported_languages(youtube)
    print(f"  YouTube 지원 언어: {len(supported_langs)}개")

    default = metadata.get("default", {})
    title = default.get("title", Path(video_path).stem)
    description = default.get("description", "")

    localizations = {}
    skipped = []
    for lang, data in metadata.items():
        if lang == "default" or not data:
            continue
        # 유효한 데이터만 포함
        loc_title = data.get("title")
        loc_desc = data.get("description")
        if not loc_title or not loc_desc:
            skipped.append(f"{lang}(데이터없음)")
            continue
        # YouTube API 언어 코드로 변환
        yt_lang = YOUTUBE_LANG_MAP.get(lang, lang)
        # 지원하지 않는 언어 건너뛰기
        if yt_lang not in supported_langs:
            skipped.append(f"{lang}(미지원)")
            continue
        localizations[yt_lang] = {
            "title": loc_title,
            "description": loc_desc,
        }

    print(f"  적용할 언어: {len(localizations)}개")
    if skipped:
        print(f"  건너뛴 언어: {', '.join(skipped)}")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",
            "defaultLanguage": default.get("language", "en"),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    if localizations:
        body["localizations"] = localizations

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    parts = "snippet,status"
    if localizations:
        parts += ",localizations"

    request = youtube.videos().insert(part=parts, body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  업로드 진행: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"영상 업로드 완료: https://youtube.com/watch?v={video_id}")

    if localizations:
        print(f"다국어 메타데이터 적용: {len(localizations)}개 언어")

    return video_id


# === Main ===

def main():
    parser = argparse.ArgumentParser(description="YouTube 다국어 영상 업로드")
    parser.add_argument("input", help="input.json 파일 경로")
    parser.add_argument("--skip-translate", action="store_true", help="번역 건너뛰기")

    args = parser.parse_args()

    # input.json 로드
    if not os.path.exists(args.input):
        print(f"오류: 입력 파일을 찾을 수 없습니다: {args.input}")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        config = json.load(f)

    # 필수 필드 확인
    video_path = config.get("video")
    title = config.get("title")
    description = config.get("description", "")

    if not video_path or not title:
        print("오류: input.json에 video와 title이 필요합니다.")
        sys.exit(1)

    # 상대 경로를 input.json 기준으로 해석
    input_dir = Path(args.input).parent
    if not os.path.isabs(video_path):
        video_path = str(input_dir / video_path)

    if not os.path.exists(video_path):
        print(f"오류: 영상 파일을 찾을 수 없습니다: {video_path}")
        sys.exit(1)

    source_lang = config.get("source_lang", DEFAULT_SOURCE_LANG)
    target_langs = config.get("langs", list(YOUTUBE_LANGUAGES.keys()))
    privacy = config.get("privacy", DEFAULT_PRIVACY)
    gemini_model = config.get("gemini_model", DEFAULT_GEMINI_MODEL)
    max_workers = config.get("max_workers", 10)

    # 프롬프트 템플릿 로드
    prompt_path = config.get("prompt")
    if prompt_path:
        if not os.path.isabs(prompt_path):
            prompt_path = str(input_dir / prompt_path)
        if os.path.exists(prompt_path):
            with open(prompt_path, encoding="utf-8") as f:
                prompt_template = f.read()
            print(f"프롬프트: {prompt_path}")
        else:
            print(f"경고: 프롬프트 파일을 찾을 수 없습니다: {prompt_path}")
            prompt_template = DEFAULT_PROMPT_TEMPLATE
    else:
        prompt_template = DEFAULT_PROMPT_TEMPLATE

    # 원본 언어 제외
    target_langs = [lang for lang in target_langs if lang != source_lang]

    print("=" * 50)
    print("YouTube 다국어 영상 업로드")
    print("=" * 50)
    print(f"영상: {video_path}")
    print(f"제목: {title}")
    print(f"언어: {source_lang} → {len(target_langs)}개 언어로 번역")
    print(f"공개: {privacy}")
    print()

    # 번역
    if args.skip_translate:
        print("번역 건너뛰기")
        metadata = {
            "default": {
                "title": title,
                "description": description,
                "language": source_lang,
            }
        }
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("오류: GEMINI_API_KEY 환경변수가 필요합니다.")
            sys.exit(1)

        client = genai.Client(api_key=api_key)

        print(f"번역 시작: {len(target_langs)}개 언어 (모델: {gemini_model}, 병렬: {max_workers})")
        metadata = translate_metadata(client, title, description, source_lang, target_langs, gemini_model, prompt_template, max_workers)
        print()

        # 메타데이터 저장
        metadata_path = input_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"메타데이터 저장: {metadata_path}")

    # 업로드
    youtube = get_authenticated_service()
    video_id = upload_video(youtube, video_path, metadata, privacy)

    # 결과
    print()
    print("=" * 50)
    print("완료")
    print("=" * 50)
    print(f"영상 ID: {video_id}")
    print(f"영상 URL: https://youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
