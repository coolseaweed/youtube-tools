#!/usr/bin/env python3
"""
YouTube 다국어 자막 일괄 업로드 스크립트

사용법:
    # 영상 업로드 + 자막 + 다국어 메타데이터
    python upload.py video.mp4 --captions ./captions/

    # 기존 영상에 자막만 추가
    python upload.py --video-id "VIDEO_ID" --captions ./captions/
"""

import argparse
import json
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = "token.json"


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
                print("Google Cloud Console에서 OAuth 자격증명을 다운로드하세요.")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def load_metadata(captions_dir: str) -> dict | None:
    """captions 폴더에서 metadata.json 로드"""
    metadata_path = Path(captions_dir) / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def upload_video(
    youtube, video_path: str, metadata: dict | None, privacy: str
) -> str:
    """영상 업로드 후 video_id 반환"""
    print(f"영상 업로드 중: {video_path}")

    # 기본 제목/설명
    default = metadata.get("default", {}) if metadata else {}
    title = default.get("title", Path(video_path).stem)
    description = default.get("description", "")

    # localizations 구성 (default 제외)
    localizations = {}
    if metadata:
        for lang, data in metadata.items():
            if lang != "default":
                localizations[lang] = {
                    "title": data.get("title", title),
                    "description": data.get("description", description),
                }

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",  # People & Blogs
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
        print(f"다국어 메타데이터 적용: {', '.join(localizations.keys())}")

    return video_id


def update_localizations(youtube, video_id: str, metadata: dict) -> bool:
    """기존 영상에 다국어 메타데이터 업데이트"""
    try:
        # 기존 영상 정보 가져오기
        video_response = youtube.videos().list(
            part="snippet,localizations", id=video_id
        ).execute()

        if not video_response.get("items"):
            print(f"오류: 영상을 찾을 수 없습니다: {video_id}")
            return False

        video = video_response["items"][0]
        snippet = video["snippet"]

        # localizations 구성
        localizations = {}
        default = metadata.get("default", {})

        for lang, data in metadata.items():
            if lang != "default":
                localizations[lang] = {
                    "title": data.get("title", snippet["title"]),
                    "description": data.get("description", snippet.get("description", "")),
                }

        if not localizations:
            return True

        # 업데이트
        body = {
            "id": video_id,
            "snippet": {
                "title": default.get("title", snippet["title"]),
                "description": default.get("description", snippet.get("description", "")),
                "categoryId": snippet["categoryId"],
            },
            "localizations": localizations,
        }

        youtube.videos().update(part="snippet,localizations", body=body).execute()

        print(f"다국어 메타데이터 업데이트: {', '.join(localizations.keys())}")
        return True

    except Exception as e:
        print(f"메타데이터 업데이트 오류: {e}")
        return False


def upload_caption(youtube, video_id: str, caption_path: Path, language: str) -> bool:
    """단일 자막 파일 업로드"""
    try:
        body = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": language,
                "isDraft": False,
            }
        }

        media = MediaFileUpload(str(caption_path), mimetype="application/x-subrip")

        youtube.captions().insert(part="snippet", body=body, media_body=media).execute()

        return True
    except Exception as e:
        print(f"  오류 ({language}): {e}")
        return False


def upload_captions(youtube, video_id: str, captions_dir: str) -> tuple[list, list]:
    """자막 폴더 내 모든 SRT 파일 업로드"""
    captions_path = Path(captions_dir)
    srt_files = sorted(captions_path.glob("*.srt"))

    if not srt_files:
        print(f"경고: {captions_dir}에 SRT 파일이 없습니다.")
        return [], []

    print(f"\n자막 업로드 시작: {len(srt_files)}개 파일")

    success = []
    failed = []

    for srt_file in srt_files:
        language = srt_file.stem  # 파일명에서 확장자 제외 = 언어코드
        print(f"  [{language}] {srt_file.name}...", end=" ")

        if upload_caption(youtube, video_id, srt_file, language):
            print("완료")
            success.append(language)
        else:
            failed.append(language)

    return success, failed


def main():
    parser = argparse.ArgumentParser(description="YouTube 다국어 자막 일괄 업로드")

    parser.add_argument("video", nargs="?", help="업로드할 영상 파일 경로")
    parser.add_argument("--video-id", help="기존 영상 ID (자막만 추가할 경우)")
    parser.add_argument("--captions", required=True, help="자막 폴더 경로 (metadata.json 포함)")
    parser.add_argument(
        "--privacy",
        default="private",
        choices=["public", "unlisted", "private"],
        help="공개 설정 (기본: private)",
    )

    args = parser.parse_args()

    # 유효성 검사
    if not args.video_id and not args.video:
        parser.error("영상 파일이 필요하거나, --video-id를 지정해야 합니다.")

    if args.video and not os.path.exists(args.video):
        print(f"오류: 영상 파일을 찾을 수 없습니다: {args.video}")
        sys.exit(1)

    if not os.path.isdir(args.captions):
        print(f"오류: 자막 폴더를 찾을 수 없습니다: {args.captions}")
        sys.exit(1)

    # 메타데이터 로드
    metadata = load_metadata(args.captions)
    if metadata:
        print(f"메타데이터 로드: {args.captions}/metadata.json")

    # 인증
    youtube = get_authenticated_service()

    # 영상 업로드 또는 기존 ID 사용
    if args.video_id:
        video_id = args.video_id
        print(f"기존 영상 사용: {video_id}")

        # 기존 영상에 메타데이터 업데이트
        if metadata:
            update_localizations(youtube, video_id, metadata)
    else:
        video_id = upload_video(youtube, args.video, metadata, args.privacy)

    # 자막 업로드
    success, failed = upload_captions(youtube, video_id, args.captions)

    # 결과 출력
    print("\n" + "=" * 50)
    print("업로드 결과")
    print("=" * 50)
    print(f"영상 ID: {video_id}")
    print(f"영상 URL: https://youtube.com/watch?v={video_id}")
    print(f"자막 성공: {len(success)}개 - {', '.join(success) if success else '없음'}")
    print(f"자막 실패: {len(failed)}개 - {', '.join(failed) if failed else '없음'}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
